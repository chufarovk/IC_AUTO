# TASK: Make 1C API responses tolerant (normalize any 1C JSON/text)

## Why

Интеграция с 1С возвращает **непредсказуемые** форматы: чистый JSON, XDTO-JSON (`#type/#value`, пары `{"name":...,"Value":...}`), массивы строк и даже текстовые пары `key=value`. Наш код ломается с ошибкой `string indices must be integers, not 'str'`. Нужно сделать слой нормализации, чтобы **любой** ответ 1С приводился к стабильной структуре, с которой работает наш пайплайн внутреннего пополнения.

## Scope

1. Добавить модуль нормализации ответов 1С.
2. Использовать нормализатор во всех местах, где мы дергаем `/hs/integrationapi/deficit/{warehouseID}` и `/hs/integrationapi/stock/{warehouseID}/{productID}`.
3. Сохранить текущую бизнес-логику; меняется только парсинг ответов.
4. Покрыть тестами (pytest) основные входные форматы.

---

## Deliverables

* Новый модуль `onec_json_normalizer.py` (см. ниже — готовый код).
* Обновлённые функции выборки `fetch_deficit(...)` и `fetch_stock(...)` (или эквивалент в нашем коде), использующие нормализатор.
* 6 юнит-тестов (pytest) на разные форматы ответов.
* Фича-флаг `ONEC_LOSSY_NORMALIZE=true` (env) c логгированием, если данные были «подлечены».
* Докстрока в месте использования, что теперь мы принимаем «всё разумное» от 1С.

---

## Constraints & Notes

* Язык: Python 3.10+.
* Библиотека HTTP: мы используем `httpx` (оставить).
* Никаких внешних зависимостей для нормализатора.
* Нормализатор **не** меняет бизнес-логику подсчёта дефицита; лишь приводит сырой ответ к канонической форме.

---

## Canonical shapes after normalization

* `/deficit` → `List[Dict]` со схемой:

  ```json
  [{"id":"<uuid>","name":"<str>","min_stock":<number>,"max_stock":<number>,"current_stock":<number>,"deficit":<number>}]
  ```

  `deficit` вычисляется, если отсутствует: `max(min_stock - current_stock, 0)`.
* `/stock` → `float` (число остатка).

---

## Add file: `app/integrations/onec_json_normalizer.py`

**Create exactly this file with this content:**

```python
# app/integrations/onec_json_normalizer.py
# Tolerant parser for 1C responses (plain JSON, XDTO JSON, string arrays, key=value text).
# No external deps.

import json, os, re
from typing import Any, Dict, List, Tuple

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

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
    """Collapse 1C XDTO nodes (#type/#value, name/Value) to plain Python types."""
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
        if v is None: return None
        if isinstance(v, (int, float)): return float(v)
        if isinstance(v, str) and _NUM_RE.fullmatch(v.strip()):
            return float(v)
    except Exception:
        return None
    return None

def normalize_deficit_payload(text: str, lossy: bool | None = None) -> List[Dict[str, Any]]:
    """
    Normalize /deficit payload to:
      [{"id": "...", "name": "...", "min_stock": <num>, "max_stock": <num>, "current_stock": <num>, "deficit": <num>}]
    """
    lossy = os.getenv("ONEC_LOSSY_NORMALIZE", "true").lower() in ("1", "true", "yes") if lossy is None else lossy
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
        if isinstance(item, str):
            item = _try_json(item) or _parse_kv_string(item)
        elif not isinstance(item, dict):
            item = {"value": item}

        canon: Dict[str, Any] = {}
        for k, v in list(item.items()):
            kl = k.lower()
            if kl in ("productid", "id"):
                canon["id"] = str(v)
            elif kl in ("name", "productname", "наименование"):
                canon["name"] = str(v)
            elif kl in ("min_stock", "minstock", "min", "minimum", "минимальныйзапас", "минимальноеколичествозапаса"):
                n = _coerce_num(v)
                if n is not None: canon["min_stock"] = n
            elif kl in ("max_stock", "maxstock", "max", "maximum", "максимальныйзапас", "максимальноеколичествозапаса"):
                n = _coerce_num(v)
                if n is not None: canon["max_stock"] = n
            elif kl in ("current_stock", "stock", "остаток", "текущийостаток", "вналичииостаток"):
                n = _coerce_num(v); 
                if n is not None: canon["current_stock"] = n
            elif kl in ("deficit", "дефицит"):
                n = _coerce_num(v); 
                if n is not None: canon["deficit"] = n

        # Compute deficit if missing
        if "deficit" not in canon:
            ms = _coerce_num(canon.get("min_stock")) or 0.0
            cs = _coerce_num(canon.get("current_stock")) or 0.0
            canon["deficit"] = ms - cs if ms > cs else 0.0

        # If lossy, fill id/name from value if absent
        if lossy:
            if "id" not in canon and "value" in item:
                canon["id"] = str(item["value"])
            if "name" not in canon and "id" in canon:
                canon["name"] = canon.get("name") or canon["id"]

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
        n = _coerce_num(data)
        if n is not None:
            return n
    if isinstance(data, list) and data:
        return normalize_stock(json.dumps(data[0]))
    raise ValueError(f"Cannot interpret /stock response: {data!r}")
```

---

## Modify: use normalizer in our 1C client

Find the code that calls 1C endpoints for internal replenishment (look for log messages like “Запуск процесса внутреннего пополнения”, “Дефицит товаров не обнаружен”). Update like this:

```python
# app/services/internal_replenishment.py  (example path)

import httpx
from app.integrations.onec_json_normalizer import normalize_deficit_payload, normalize_stock

ONEC_BASE = "http://84.23.42.102/businessmedia_ut/hs/integrationapi"

def fetch_deficit(warehouse_id: str) -> list[dict]:
    url = f"{ONEC_BASE}/deficit/{warehouse_id}"
    r = httpx.get(url, timeout=30.0)
    r.raise_for_status()
    data = normalize_deficit_payload(r.text)
    # Optional: debug log first item
    if data:
        print(f"[deficit] normalized first: {data[0]}")
    return data

def fetch_stock(warehouse_id: str, product_id: str) -> float:
    url = f"{ONEC_BASE}/stock/{warehouse_id}/{product_id}"
    r = httpx.get(url, timeout=30.0)
    r.raise_for_status()
    return normalize_stock(r.text)

# usage inside your pipeline:
def run_internal_replenishment(warehouse_id: str):
    items = fetch_deficit(warehouse_id)
    if not items:
        # log "Дефицит товаров не обнаружен. Процесс завершен."
        return
    for it in items:
        pid = it.get("id")
        deficit_qty = float(it.get("deficit") or 0)
        # ... rest of your logic
```

If you have a class-based client – inject the normalizer result in the composing method; structure stays the same.

---

## Tests (pytest)

Create `tests/test_onec_normalizer.py` with:

```python
import json
from app.integrations.onec_json_normalizer import normalize_deficit_payload, normalize_stock

def test_deficit_plain_json():
    raw = json.dumps([{"id":"u1","name":"A","min_stock":10,"max_stock":50,"current_stock":3}])
    out = normalize_deficit_payload(raw)
    assert out[0]["deficit"] == 7

def test_deficit_xdto_pair_list():
    raw = json.dumps({"#value":[
        {"name":{"#value":"id"},"Value":{"#value":"u2"}},
        {"name":{"#value":"name"},"Value":{"#value":"B"}},
        {"name":{"#value":"min_stock"},"Value":{"#value":5}},
        {"name":{"#value":"current_stock"},"Value":{"#value":2}}
    ]})
    out = normalize_deficit_payload(raw)
    assert out[0]["id"] == "u2" and out[0]["deficit"] == 3

def test_deficit_kv_text_lines():
    raw = 'id=u3, name=C, min_stock=8, current_stock=1\nid=u4, name=D, min: 3, current_stock: 5'
    out = normalize_deficit_payload(raw)
    assert out[0]["deficit"] == 7 and out[1]["deficit"] == 0

def test_stock_plain():
    assert normalize_stock('{"stock": 12.5}') == 12.5

def test_stock_xdto():
    raw = json.dumps({"#type":"jxs:number","#value": "3"})
    assert normalize_stock(raw) == 3.0

def test_stock_number_string():
    assert normalize_stock("  4.75 ") == 4.75
```

---

## Logging & Feature flag

* Add env var `ONEC_LOSSY_NORMALIZE` (default `true`). When true, `normalize_deficit_payload`:

  * заполняет пустые `id`/`name` «как есть» из `value` (если пришла странная форма),
  * это позволяет не падать, но логируйте debug-сообщение в вашем логгере при «lossy repair» (можете обернуть нормализатор, если нужен централизованный лог).
* Ensure we log first 200 chars of raw 1C response at DEBUG level (not INFO!) только при включённом детальном логировании.

---

## Acceptance criteria

* Ошибка `string indices must be integers, not 'str'` больше не появляется в процессе `InternalReplenishment`.
* При любых из поддерживаемых форм ответов 1С (plain JSON, XDTO JSON, массив строк, key=value текст) наш пайплайн корректно:

  * получает список дефицитов (минимум 1 позиция — воспроизводимый тест-кейс),
  * получает число остатка.
* Юнит-тесты проходят локально и в CI.
* Логи содержат аккуратное debug-сообщение о нормализации (без PII/секретов).

---

## Out of scope (for now)

* Менять 1С-код на сервере.
* Менять бизнес-правила пополнения.

---

### Notes to the AI-coder

Готовый код нормализатора — выше. Внедрите его без изменения внешнего контракта наших внутренний функций: upstream код должен по-прежнему получать `list[dict]` для дефицита и `float` для остатка. Если в проекте функционал разбросан по нескольким файлам — создайте thin-adapter `OneCClient` и используйте его в сервисах, чтобы в одном месте была нормализация.

Если в процессе интеграции встретите новый экзотический формат — добавьте минимальный тест + ветку в `_unwrap_xdto` или `_parse_kv_string`.
