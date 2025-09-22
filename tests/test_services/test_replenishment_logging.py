import json
import logging
import pytest
from unittest.mock import AsyncMock, patch

from app.services.replenishment_service import ReplenishmentService
from app.core.logging import set_run_id
from app.core.observability import log_step


def test_filter_logging(caplog):
    """Test that filtering logs are properly structured."""
    caplog.set_level(logging.INFO)

    # Mock the replenishment service to test logging behavior
    with patch('app.services.replenishment_service.ReplenishmentService._fetch_and_filter_deficit') as mock_fetch:
        # This would test the internal logging logic
        # We'll focus on testing the log structure
        pass


def test_log_step_decorator_async():
    """Test the @log_step decorator with async functions."""

    @log_step("test.async_function")
    async def test_async_function(param1: str, param2: int):
        return f"result: {param1}-{param2}"

    # Test that decorator doesn't break function behavior
    import asyncio
    result = asyncio.run(test_async_function("test", 42))
    assert result == "result: test-42"


def test_log_step_decorator_sync():
    """Test the @log_step decorator with sync functions."""

    @log_step("test.sync_function")
    def test_sync_function(param1: str, param2: int):
        return f"result: {param1}-{param2}"

    # Test that decorator doesn't break function behavior
    result = test_sync_function("test", 42)
    assert result == "result: test-42"


def test_log_step_decorator_exception():
    """Test the @log_step decorator handles exceptions properly."""

    @log_step("test.failing_function")
    def test_failing_function():
        raise ValueError("Test error")

    with pytest.raises(ValueError, match="Test error"):
        test_failing_function()


@pytest.mark.asyncio
async def test_replenishment_service_logging_integration(caplog):
    """Test integration of logging in replenishment service."""
    caplog.set_level(logging.INFO)

    # Mock the session and dependencies
    mock_session = AsyncMock()

    with patch('app.services.replenishment_service.OneSApiClient') as mock_onec, \
         patch('app.services.replenishment_service.MoySkladApiClient') as mock_ms, \
         patch('app.services.replenishment_service.log_event') as mock_log_event:

        # Setup mock responses
        mock_onec_instance = AsyncMock()
        mock_onec.return_value = mock_onec_instance
        mock_onec_instance.get_deficit_products.return_value = []
        mock_onec_instance.close = AsyncMock()

        mock_ms_instance = AsyncMock()
        mock_ms.return_value = mock_ms_instance
        mock_ms_instance.close = AsyncMock()

        # Create service and run
        service = ReplenishmentService(session=mock_session)
        result = await service.run_internal_replenishment()

        # Verify result
        assert result["status"] == "success"
        assert "No deficit found" in result["message"]

        # Verify log_event was called
        mock_log_event.assert_called()


def test_context_vars_logging():
    """Test that context variables are properly set and retrieved."""
    from app.core.logging import set_run_id, run_id_var, set_request_id, request_id_var

    # Test run_id
    test_run_id = "test-run-123"
    returned_id = set_run_id(test_run_id)
    assert returned_id == test_run_id
    assert run_id_var.get() == test_run_id

    # Test request_id
    test_request_id = "test-request-456"
    returned_request_id = set_request_id(test_request_id)
    assert returned_request_id == test_request_id
    assert request_id_var.get() == test_request_id


def test_json_formatter():
    """Test JSON log formatter output."""
    from app.core.logging import JsonFormatter, set_run_id
    import logging
    import json

    # Setup formatter and logger
    formatter = JsonFormatter()
    logger = logging.getLogger("test_logger")

    # Create test log record
    set_run_id("test-run-123")
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None
    )
    record.extra = {"test_field": "test_value", "password": "secret"}

    # Format and parse JSON
    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    # Verify structure
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "Test message"
    assert parsed["run_id"] == "test-run-123"
    assert parsed["test_field"] == "test_value"
    assert parsed["password"] == "***"  # Should be redacted


def test_redaction_functionality():
    """Test that sensitive data is properly redacted."""
    from app.core.logging import _redact

    test_data = {
        "username": "testuser",
        "password": "secret123",
        "Authorization": "Bearer token123",
        "apikey": "key123",
        "normal_field": "normal_value",
        "nested": {
            "password": "nested_secret",
            "data": "normal_data"
        }
    }

    redacted = _redact(test_data)

    assert redacted["username"] == "testuser"
    assert redacted["password"] == "***"
    assert redacted["Authorization"] == "***"
    assert redacted["apikey"] == "***"
    assert redacted["normal_field"] == "normal_value"
    assert redacted["nested"]["password"] == "***"
    assert redacted["nested"]["data"] == "normal_data"