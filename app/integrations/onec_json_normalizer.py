# app/integrations/onec_json_normalizer.py
# Tolerant parser for 1C responses (plain JSON, XDTO JSON, string arrays, key=value text).
# No external deps.

import json
import os
import re
from typing import Any, Dict, List

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
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
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
            elif kl in ("deficit", "дефицит"):
                n = _coerce_num(v)
                if n is not None:
                    canon["deficit"] = n

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