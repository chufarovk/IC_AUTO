# app/integrations/onec_json_normalizer.py
# Tolerant parser for 1C responses (plain JSON, XDTO JSON, string arrays, key=value text).
# Guarantees id/name in normalize_deficit_payload (with surrogate id if needed).
# No external deps.

import hashlib
import json
import logging
import os
import re
from decimal import Decimal
from typing import Any, Dict, List

log = logging.getLogger(__name__)


class IntegrationError(Exception):
    """Исключение для ошибок интеграции с внешними системами."""
    pass

_NUM_RE  = re.compile(r"^-?\d+(?:\.\d+)?$")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-"
    r"[0-9a-fA-F]{12}"
)

def _try_json(s: str):
    s = s.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        # Sometimes JSON is double-quoted: "\"{...}\""
        if (s[0] in "\"'" and s[-1] == s[0]):
            try:
                return json.loads(s[1:-1])
            except Exception:
                return None
        return None

def _parse_kv_string(s: str) -> Dict[str, Any]:
    """
    Parse 'id=..., name=..., min_stock:10, current_stock: 3' into dict.
    If parsing fails, return {"value": s}.
    """
    s = s.strip().strip("{}")
    out: Dict[str, Any] = {}
    for m in re.finditer(r'([A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*[:=]\s*("([^"\\]|\\.)*"|[^,;]+)', s):
        k, v = m.group(1), m.group(2).strip()
        if v.startswith('"') and v.endswith('"'):
            try:
                v = json.loads(v)
            except Exception:
                v = v[1:-1]
        else:
            v = v.strip()
            if _NUM_RE.fullmatch(v):
                v = float(v) if "." in v else int(v)
        out[k] = v
    return out or {"value": s}

def _unwrap_xdto(node: Any) -> Any:
    """Collapse 1C XDTO nodes (#type/#value, {'name':...,'Value':...}) to plain Python types."""
    if isinstance(node, dict):
        if "#value" in node and (len(node) == 1 or (len(node) == 2 and "#type" in node)):
            return _unwrap_xdto(node["#value"])
        if "name" in node and "Value" in node:
            key = _unwrap_xdto(node["name"])
            return {str(key): _unwrap_xdto(node["Value"])}
        return {k: _unwrap_xdto(v) for k, v in node.items()}
    if isinstance(node, list):
        items = [_unwrap_xdto(x) for x in node]
        # Merge list of single-key dicts into one dict (typical for XDTO)
        if all(isinstance(x, dict) and len(x) == 1 for x in items):
            merged: Dict[str, Any] = {}
            for d in items:
                for k, v in d.items():
                    merged[str(k)] = v
            return merged
        return items
    return node

def parse_1c_response(text: str) -> Any:
    """
    Returns Python object from 1C response of various shapes:
    - Plain JSON
    - XDTO JSON (#value/#type, {'name':..., 'Value':...})
    - Lines with JSON or key=value pairs
    - Dict with numeric keys acting as array
    """
    obj = _try_json(text)
    if obj is None:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) > 1:
            return [_try_json(ln) or _parse_kv_string(ln) for ln in lines]
        return _parse_kv_string(text)

    obj = _unwrap_xdto(obj)

    # Some gateways return arrays as dict {"0":..., "1":...}
    if isinstance(obj, dict) and obj and all(isinstance(k, str) and k.isdigit() for k in obj.keys()):
        try:
            return [obj[str(i)] for i in range(len(obj))]
        except Exception:
            pass

    return obj

def _coerce_num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str) and _NUM_RE.fullmatch(v.strip()):
            return float(v)
    except Exception:
        return None
    return None

def _first_uuid_from_value(v: Any) -> str | None:
    """Try to extract UUID from arbitrary value."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None
    # If dict, look for common keys
    if isinstance(v, dict):
        for key in ("id","productID","uuid","uid","guid","ref","reference","УникальныйИдентификатор","Ссылка","Номенклатура"):
            if key in v:
                u = _first_uuid_from_value(v[key])
                if u:
                    return u
        # Scan all values
        for vv in v.values():
            u = _first_uuid_from_value(vv)
            if u:
                return u
        return None
    # If list, scan
    if isinstance(v, list):
        for vv in v:
            u = _first_uuid_from_value(vv)
            if u:
                return u
        return None
    # str or other printable
    s = str(v)
    m = _UUID_RE.search(s)
    return m.group(0) if m else None

def _derive_surrogate_id(item: Dict[str, Any]) -> str:
    """Deterministic surrogate id from stable hash of the item."""
    raw = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"SURR-{h[:12]}"

def _choose_name(item: Dict[str, Any], fallback_id: str | None) -> str:
    for k in ("name","productName","Наименование","товар","product","Номенклатура"):
        if k in item and isinstance(item[k], (str,int,float)):
            return str(item[k])
        if k in item and isinstance(item[k], dict) and "name" in item[k]:
            return str(item[k]["name"])
    # Fallback to SKU if name is not found
    for k in ("sku", "article", "art", "артикул"):
        if k in item and isinstance(item[k], (str,int,float)):
            return f"SKU-{item[k]}"
    return fallback_id or "UNKNOWN"

def normalize_deficit_payload(text: str, lossy: bool | None = None) -> List[Dict[str, Any]]:
    """
    Normalize /deficit to:
      [{"id": "...", "name": "...", "min_stock": <num>, "max_stock": <num>, "current_stock": <num>, "deficit": <num>}]
    Guarantees presence of 'id' and 'name' unless STRICT_IDS=true and no UUID can be found.
    """
    lossy = os.getenv("ONEC_LOSSY_NORMALIZE", "true").lower() in ("1", "true", "yes") if lossy is None else lossy
    strict_ids = os.getenv("STRICT_IDS", "false").lower() in ("1","true","yes")

    data = parse_1c_response(text)

    # Extract list from dict containers
    if isinstance(data, dict):
        for k in ("items", "rows", "list", "value", "result", "#value"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if not isinstance(data, list):
        data = [data]

    out: List[Dict[str, Any]] = []
    for item in data:
        # Bring item to dict
        if isinstance(item, str):
            item = _try_json(item) or _parse_kv_string(item)
        elif not isinstance(item, dict):
            item = {"value": item}

        # Canonical fields
        canon: Dict[str, Any] = {}

        # Map known fields
        for k, v in list(item.items()):
            kl = k.lower()
            if kl in ("productid", "id"):
                canon["id"] = str(v)
            elif kl in ("name", "productname", "наименование"):
                canon["name"] = str(v)
            elif kl in ("sku", "article", "art", "артикул"):
                canon["sku"] = str(v)
            elif kl in ("min_stock", "minstock", "min", "minimum", "минимальныйзапас", "минимальноеколичествозапаса"):
                n = _coerce_num(v)
                if n is not None:
                    canon["min_stock"] = n
            elif kl in ("max_stock", "maxstock", "max", "maximum", "максимальныйзапас", "максимальноеколичествозапаса"):
                n = _coerce_num(v)
                if n is not None:
                    canon["max_stock"] = n
            elif kl in ("current_stock", "stock", "остаток", "текущийостаток", "вналичииостаток"):
                n = _coerce_num(v)
                if n is not None:
                    canon["current_stock"] = n
            elif kl in ("deficit", "need_to_order", "quantity_to_order", "количествокзаказу", "кколичествузаказа", "дефицит"):
                n = _coerce_num(v)
                if n is not None:
                    canon["deficit"] = n

        # Fill deficit if missing
        if "deficit" not in canon:
            ms = _coerce_num(canon.get("min_stock")) or 0.0
            cs = _coerce_num(canon.get("current_stock")) or 0.0
            canon["deficit"] = ms - cs if ms > cs else 0.0

        # Ensure ID: try to extract from any value
        if "id" not in canon or not canon["id"]:
            u = _first_uuid_from_value(item)
            if u:
                canon["id"] = u
            elif not strict_ids:
                # Create deterministic surrogate
                canon["id"] = _derive_surrogate_id(item)
                log.debug("onec.normalize: generated surrogate id %s for item %s", canon["id"], item)
            else:
                log.warning("onec.normalize: dropping item without UUID under STRICT_IDS: %s", item)
                continue  # drop item

        # Ensure name
        if "name" not in canon or not str(canon["name"]).strip():
            canon["name"] = _choose_name(item, canon.get("id"))

        out.append(canon)

    return out

def normalize_stock(text: str) -> float:
    """
    Normalize /stock to float.
    Accepts {"stock": 12.3}, {"Остаток":...}, raw number, XDTO etc.
    """
    data = parse_1c_response(text)
    if isinstance(data, dict):
        for k in ("stock", "остаток", "current_stock", "вналичииостаток", "#value", "value"):
            if k in data and not isinstance(data[k], (dict, list)):
                n = _coerce_num(data[k])
                if n is not None:
                    return n
    if isinstance(data, (int, float)):
        return float(data)
    if isinstance(data, str):
        s = data.strip()
        n = _coerce_num(s)
        if n is not None:
            return n
    if isinstance(data, list) and data:
        # try first element
        try:
            return normalize_stock(json.dumps(data[0]))
        except Exception:
            pass
    raise ValueError(f"Cannot interpret /stock response: {data!r}")


def parse_1c_json(text: str) -> dict | list:
    """
    Пытаемся распарсить ответ 1С в различных форматах:
    1) Чистый JSON: объект или список
    2) Двойной JSON (строка, внутри которой ещё JSON)
    3) XDTO-форма: {"#value":[{"name":{"#value":"error"},"Value":{"#value":"..."}} ...]}
    4) Тело с BOM/мусором по краям

    Возвращаем питоновский объект или бросаем IntegrationError с нормальным сообщением.

    Алгоритм согласно Task006.md:
    1. Сначала json.loads(text); если упало — попробовать json.loads(json.loads(text)) (двойная сериализация)
    2. Если результат — dict с ключом #value, преобразовать в нормальный dict/список
    3. Если это строка — попытаться «ещё раз» (двойной JSON)
    4. Все числовые поля привести к Decimal/float
    5. Если структура не распознана — лог и IntегrationError
    """
    try:
        # Используем существующий функционал для парсинга
        result = _try_json(text)
        if result is None:
            # Попробуем стандартный json.loads для правильной обработки null
            try:
                result = json.loads(text)
            except:
                raise IntegrationError(f"Cannot parse JSON from 1C response: {text[:200]}...")

        # Шаг 2: Проверяем XDTO-ошибку
        if isinstance(result, dict) and "#value" in result:
            xdto_list = result["#value"]
            if isinstance(xdto_list, list):
                for item in xdto_list:
                    if (isinstance(item, dict) and
                        "name" in item and
                        isinstance(item["name"], dict) and
                        item["name"].get("#value") == "error"):
                        error_message = "1C error"
                        if "Value" in item and isinstance(item["Value"], dict):
                            error_message = str(item["Value"].get("#value", "Unknown error"))
                        raise IntegrationError(f"1C API error: {error_message}")

            # Разворачиваем XDTO структуру
            result = _unwrap_xdto(result)

        # Шаг 3: Если получили строку, пробуем ещё раз
        if isinstance(result, str):
            nested_result = _try_json(result)
            if nested_result is not None:
                result = _unwrap_xdto(nested_result)

        # Шаг 4: Приводим числовые поля к Decimal/float
        result = _convert_numeric_fields(result)

        # Шаг 5: Проверяем что получили валидную структуру
        if result is None:
            raise IntegrationError("1C response is null")

        if not isinstance(result, (dict, list, str, int, float)):
            raise IntegrationError(f"Unexpected 1C response schema: {type(result)}")

        return result

    except IntegrationError:
        # Перебрасываем IntegrationError как есть
        raise
    except Exception as e:
        log.error(f"Failed to parse 1C response: {e}")
        raise IntegrationError(f"Failed to parse 1C response: {str(e)}")


def _convert_numeric_fields(obj: Any) -> Any:
    """Рекурсивно конвертирует числовые поля в Decimal/float."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # Специальные поля которые должны быть числовыми
            if key.lower() in ('min_stock', 'max_stock', 'current_stock', 'deficit', 'stock', 'остаток'):
                numeric_value = _coerce_num(value)
                if numeric_value is not None:
                    result[key] = Decimal(str(numeric_value))
                else:
                    result[key] = value
            else:
                result[key] = _convert_numeric_fields(value)
        return result
    elif isinstance(obj, list):
        return [_convert_numeric_fields(item) for item in obj]
    else:
        return obj