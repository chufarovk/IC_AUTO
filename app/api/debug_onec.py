# app/api/debug_onec.py
from fastapi import APIRouter, Depends, Header, HTTPException, Query
import httpx
from app.core.config import settings
from app.services.logger_service import log_event

router = APIRouter(prefix="/api/v1/debug/onec", tags=["debug-onec"])

def _auth(x_debug_token: str | None):
    if not settings.DEBUG_ONEC_TOKEN:
        raise HTTPException(403, "DEBUG disabled")
    if x_debug_token != settings.DEBUG_ONEC_TOKEN:
        raise HTTPException(401, "Invalid token")

def _find_expected_matches(items: list, expected_skus: list[str]) -> dict[str, int]:
    """Find matches for expected SKUs in the items list"""
    matches = {sku: 0 for sku in expected_skus}

    sku_fields = ["sku", "article", "art", "Артикул"]

    for item in items:
        if not isinstance(item, dict):
            continue

        # Check SKU fields
        item_sku = None
        for field in sku_fields:
            if field in item and item[field]:
                item_sku = str(item[field]).strip()
                break

        # Check name field for SKU
        if not item_sku and "name" in item and item["name"]:
            item_name = str(item["name"])
            for expected_sku in expected_skus:
                if expected_sku in item_name:
                    item_sku = expected_sku
                    break

        # Count matches
        if item_sku:
            for expected_sku in expected_skus:
                if expected_sku == item_sku:
                    matches[expected_sku] += 1

    return matches

def _mask_sensitive_headers(headers: dict) -> dict:
    """Mask sensitive information in headers"""
    masked = {}
    sensitive_keys = {"authorization", "auth", "password", "token", "key", "secret"}

    for key, value in headers.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            masked[key] = "***MASKED***"
        else:
            masked[key] = value
    return masked

@router.get("/deficit")
async def get_deficit_raw(
    warehouse_id: str = Query(..., description="UUID склада"),
    expected_skus: str = Query(default="AV-04362,AV-04172,AV-04964", description="Expected SKUs (CSV)"),
    x_debug_token: str | None = Header(None),
):
    _auth(x_debug_token)

    url = f"{settings.ONEC_BASE_URL}/hs/integrationapi/deficit/{warehouse_id}"
    expected_sku_list = [sku.strip() for sku in expected_skus.split(",") if sku.strip()]

    # ВАЖНО: та же авторизация, что в основном сервисе
    async with httpx.AsyncClient(
        timeout=30,
        auth=httpx.BasicAuth(settings.API_1C_USER, settings.API_1C_PASSWORD),
        headers={"Accept": "application/json"},
    ) as client:
        r = await client.get(url)

    # Capture raw response details
    raw_text = r.text[:65535]  # Limit raw text to 64KB
    content_type = r.headers.get("Content-Type", "unknown")

    # Handle non-200 responses
    if r.status_code != 200:
        await log_event(
            step="replenishment.fetch_deficit.error",
            status="ERROR",
            external_system="ONEC",
            details={
                "status_code": r.status_code,
                "content_type": content_type,
                "url": str(r.url),
                "raw_text_preview": raw_text[:2048],
                "warehouse_id": warehouse_id,
            }
        )

        return {
            "status_code": r.status_code,
            "content_type": content_type,
            "url": str(r.url),
            "error": "Non-200 response from 1C",
            "raw_text_preview": raw_text[:2048],
        }

    # Try to parse JSON
    try:
        raw = r.json()
        json_parsed = True
        payload_data = raw
    except Exception:
        raw = {"_parse_error": True, "text": raw_text}
        json_parsed = False
        payload_data = None

    # Нормализация форматов: list | {"value":[...]} | {"#value":[...]} | {"data":[...]}
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict) and not raw.get("_parse_error"):
        items = (
            raw.get("value")
            or raw.get("#value")
            or raw.get("data")
            or []
        )
        if not isinstance(items, list):
            items = []
    else:
        items = []

    # Analyze items for expected SKUs
    expected_matches = _find_expected_matches(items, expected_sku_list)

    # Get first item and raw keys for analysis
    raw_first_item = items[0] if items else None
    raw_keys = list(raw.keys()) if isinstance(raw, dict) and not raw.get("_parse_error") else None

    # Prepare details for logging
    details = {
        "status_code": r.status_code,
        "content_type": content_type,
        "url": str(r.url),
        "raw_text_preview": raw_text[:4096],  # First 4KB for analysis
        "items_count": len(items),
        "raw_keys": raw_keys,
        "raw_first_item": raw_first_item,
        "expected_matches": expected_matches,
        "expected_skus": expected_sku_list,
        "warehouse_id": warehouse_id,
        "json_parsed": json_parsed,
    }

    await log_event(
        step="replenishment.fetch_deficit.raw",
        status="INFO",
        external_system="ONEC",
        details=details,
        payload=payload_data if json_parsed else None,
    )

    return {
        "status_code": r.status_code,
        "content_type": content_type,
        "url": str(r.url),
        "headers": _mask_sensitive_headers(dict(r.headers)),
        "items_count": len(items),
        "raw_keys": raw_keys,
        "raw_first_item": raw_first_item,
        "expected_matches": expected_matches,
        "sample": items[:3],
        "json_parsed": json_parsed,
    }