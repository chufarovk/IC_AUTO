import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.integrations.base_client import BaseApiClient


@pytest.mark.asyncio
async def test_http_logging_success(caplog):
    """Test HTTP request logging for successful requests."""
    import logging
    caplog.set_level(logging.DEBUG)

    # Mock httpx client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"result": "success"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"result": "success"}

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_client.request.return_value = mock_response

        # Create client and make request
        client = BaseApiClient("https://api.example.com")
        result = await client._request("GET", "/test")

        # Verify result
        assert result == {"result": "success"}

        # Check logs contain expected fields
        log_records = [record for record in caplog.records if record.name == "http"]
        assert len(log_records) >= 1

        # Find the success log
        success_logs = [r for r in log_records if "-> 200" in r.message]
        assert len(success_logs) == 1

        success_log = success_logs[0]
        assert hasattr(success_log, 'extra')
        extra = success_log.extra.get('extra', {})
        assert extra['method'] == 'GET'
        assert extra['status_code'] == 200
        assert 'elapsed_ms' in extra
        assert 'response_preview' in extra
        assert 'response_hash' in extra


@pytest.mark.asyncio
async def test_http_logging_with_headers_redaction():
    """Test that sensitive headers are redacted in logs."""
    import logging

    # Mock httpx client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"result": "ok"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"result": "ok"}

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_client.request.return_value = mock_response

        client = BaseApiClient("https://api.example.com")

        # Capture logs at debug level to see request details
        with patch.object(client._logger, 'debug') as mock_debug:
            await client._request("POST", "/test", headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
                "X-API-Key": "secret-key"
            })

            # Check that debug was called with redacted headers
            mock_debug.assert_called()
            call_args = mock_debug.call_args
            extra_data = call_args[1]['extra']['extra']
            headers = extra_data['headers']

            assert headers['Authorization'] == '***'
            assert headers['X-API-Key'] == '***'  # Should be redacted (apikey variant)
            assert headers['Content-Type'] == 'application/json'  # Should not be redacted


@pytest.mark.asyncio
async def test_http_logging_error_handling():
    """Test HTTP error logging."""
    import logging

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock a HTTP error
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        http_error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=error_response)
        mock_client.request.side_effect = http_error

        client = BaseApiClient("https://api.example.com")

        with patch.object(client._logger, 'error') as mock_error:
            with pytest.raises(httpx.HTTPStatusError):
                await client._request("GET", "/test")

            # Verify error logging
            mock_error.assert_called()
            call_args = mock_error.call_args
            assert "HTTP FAIL" in call_args[0][0]
            extra_data = call_args[1]['extra']['extra']
            assert extra_data['method'] == 'GET'
            assert 'elapsed_ms' in extra_data
            assert 'attempts' in extra_data


@pytest.mark.asyncio
async def test_http_response_sampling():
    """Test response body sampling based on LOG_SAMPLE_RATE."""
    import os

    # Test with full sampling
    with patch.dict(os.environ, {'LOG_SAMPLE_RATE': '1.0'}):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = 'full response body'
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {}

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.request.return_value = mock_response

            client = BaseApiClient("https://api.example.com")

            with patch.object(client._logger, 'info') as mock_info:
                await client._request("GET", "/test")

                call_args = mock_info.call_args
                extra_data = call_args[1]['extra']['extra']
                assert extra_data['response_preview'] == 'full response body'

    # Test with no sampling
    with patch.dict(os.environ, {'LOG_SAMPLE_RATE': '0.0'}):
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.request.return_value = mock_response

            client = BaseApiClient("https://api.example.com")

            with patch.object(client._logger, 'info') as mock_info:
                await client._request("GET", "/test")

                call_args = mock_info.call_args
                extra_data = call_args[1]['extra']['extra']
                assert '[sampled hash:' in extra_data['response_preview']


def test_response_hash_generation():
    """Test response body hash generation."""
    client = BaseApiClient("https://api.example.com")

    test_body = "test response content"
    hash_result = client._maybe_hash(test_body)

    # Should return a 16-character hex string
    assert len(hash_result) == 16
    assert all(c in '0123456789abcdef' for c in hash_result)

    # Same input should produce same hash
    assert client._maybe_hash(test_body) == hash_result


@pytest.mark.asyncio
async def test_retry_logic_with_logging():
    """Test retry logic and logging."""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        # First call fails, second succeeds
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.text = "Service Unavailable"
        http_error = httpx.HTTPStatusError("Service Error", request=MagicMock(), response=error_response)

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.text = '{"result": "ok"}'
        success_response.headers = {"content-type": "application/json"}
        success_response.json.return_value = {"result": "ok"}

        mock_client.request.side_effect = [http_error, success_response]

        client = BaseApiClient("https://api.example.com")

        with patch('asyncio.sleep'):  # Speed up test by mocking sleep
            result = await client._request_with_retry("GET", "/test", tries=2)

        assert result == {"result": "ok"}

        # Should have made 2 requests (1 fail + 1 success)
        assert mock_client.request.call_count == 2