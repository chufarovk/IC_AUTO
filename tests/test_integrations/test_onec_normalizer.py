import json
import pytest
from decimal import Decimal
from app.integrations.onec_json_normalizer import parse_1c_json, IntegrationError


class TestParse1CJson:
    """Тесты для функции parse_1c_json с фикстурами 4 форматов согласно Task006.md."""

    def test_empty_array_no_deficit(self):
        """Тест 1: [] (дефицита нет) - не ошибка."""
        response = "[]"
        result = parse_1c_json(response)
        assert result == []

    def test_valid_array_of_objects(self):
        """Тест 2: валидный массив объектов."""
        response = '''[
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Товар 1",
                "min_stock": 10,
                "max_stock": 100,
                "current_stock": 5,
                "deficit": 5
            },
            {
                "id": "987fcdeb-51d3-12b4-c567-426614174001",
                "name": "Товар 2",
                "min_stock": 20.5,
                "max_stock": 200.0,
                "current_stock": 15.5,
                "deficit": 5.0
            }
        ]'''
        result = parse_1c_json(response)

        assert isinstance(result, list)
        assert len(result) == 2

        # Проверяем первый элемент
        item1 = result[0]
        assert item1["id"] == "123e4567-e89b-12d3-a456-426614174000"
        assert item1["name"] == "Товар 1"
        assert isinstance(item1["min_stock"], Decimal)
        assert item1["min_stock"] == Decimal("10")
        assert isinstance(item1["current_stock"], Decimal)
        assert item1["current_stock"] == Decimal("5")

    def test_xdto_error_format(self):
        """Тест 3: XDTO-ошибка (#value → error)."""
        response = '''{
            "#value": [
                {
                    "name": {"#value": "error"},
                    "Value": {"#value": "Товар не найден в базе"}
                }
            ]
        }'''

        with pytest.raises(IntegrationError) as exc_info:
            parse_1c_json(response)

        assert "1C API error: Товар не найден в базе" in str(exc_info.value)

    def test_double_json_string(self):
        """Тест 4: двойной JSON/строка."""
        # Двойная сериализация JSON
        inner_json = '{"stock": 25.5, "available": true}'
        double_json = f'"{inner_json}"'

        result = parse_1c_json(double_json)

        assert isinstance(result, dict)
        assert isinstance(result["stock"], Decimal)
        assert result["stock"] == Decimal("25.5")
        assert result["available"] == True

    def test_xdto_success_format(self):
        """Тест: успешный XDTO формат."""
        response = '''{
            "#value": {
                "items": [
                    {
                        "id": {"#value": "abc123"},
                        "name": {"#value": "Тестовый товар"},
                        "stock": {"#value": "15.0"}
                    }
                ]
            }
        }'''

        result = parse_1c_json(response)

        assert isinstance(result, dict)
        assert "items" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "abc123"
        assert result["items"][0]["name"] == "Тестовый товар"
        assert isinstance(result["items"][0]["stock"], Decimal)

    def test_numeric_field_conversion(self):
        """Тест: конвертация числовых полей в Decimal."""
        response = '''{
            "min_stock": "10.5",
            "max_stock": 100,
            "current_stock": "15.75",
            "deficit": 0,
            "other_field": "not_a_number"
        }'''

        result = parse_1c_json(response)

        assert isinstance(result["min_stock"], Decimal)
        assert result["min_stock"] == Decimal("10.5")
        assert isinstance(result["max_stock"], Decimal)
        assert result["max_stock"] == Decimal("100")
        assert isinstance(result["current_stock"], Decimal)
        assert result["current_stock"] == Decimal("15.75")
        assert isinstance(result["deficit"], Decimal)
        assert result["deficit"] == Decimal("0")
        # Поле которое не является числовым - не конвертируется
        assert result["other_field"] == "not_a_number"

    def test_invalid_json_format(self):
        """Тест: некорректный JSON вызывает IntegrationError."""
        response = '{"invalid": json format}'

        with pytest.raises(IntegrationError) as exc_info:
            parse_1c_json(response)

        assert "Cannot parse JSON from 1C response" in str(exc_info.value)

    def test_null_response(self):
        """Тест: null ответ вызывает IntegrationError."""
        response = 'null'

        with pytest.raises(IntegrationError) as exc_info:
            parse_1c_json(response)

        assert "1C response is null" in str(exc_info.value)

    def test_complex_xdto_structure(self):
        """Тест: сложная XDTO структура с вложенными объектами."""
        response = '''{
            "#value": [
                {
                    "name": {"#value": "product"},
                    "Value": {
                        "#value": {
                            "id": {"#value": "prod-001"},
                            "details": {
                                "#value": {
                                    "min_stock": {"#value": "50.25"},
                                    "current_stock": {"#value": "25.0"}
                                }
                            }
                        }
                    }
                }
            ]
        }'''

        result = parse_1c_json(response)

        assert isinstance(result, dict)
        # После разворачивания XDTO структуры должны остаться нормальные значения
        assert "product" in result
        product_data = result["product"]
        assert product_data["id"] == "prod-001"
        assert isinstance(product_data["details"]["min_stock"], Decimal)
        assert product_data["details"]["min_stock"] == Decimal("50.25")

    def test_string_response_that_is_not_json(self):
        """Тест: строковый ответ который не является JSON."""
        response = '"simple string response"'

        result = parse_1c_json(response)

        assert result == "simple string response"

    def test_nested_double_json(self):
        """Тест: вложенный двойной JSON - более реальный случай."""
        # Более реалистичный сценарий: 1С возвращает строку с JSON внутри
        inner_data = {"stock": 42, "warehouse": "main"}
        response = json.dumps(json.dumps(inner_data))  # Двойная сериализация

        result = parse_1c_json(response)

        assert isinstance(result, dict)
        assert isinstance(result["stock"], Decimal)
        assert result["stock"] == Decimal("42")
        assert result["warehouse"] == "main"


if __name__ == "__main__":
    pytest.main([__file__])