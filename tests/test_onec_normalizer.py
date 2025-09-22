import json
from app.integrations.onec_json_normalizer import (
    normalize_deficit_payload, normalize_stock, _UUID_RE
)

def test_deficit_plain_json_has_deficit():
    raw = json.dumps([{"id":"u1","name":"A","min_stock":10,"current_stock":3}])
    out = normalize_deficit_payload(raw)
    assert out[0]["deficit"] == 7

def test_deficit_missing_id_generates_surrogate(monkeypatch):
    monkeypatch.setenv("STRICT_IDS", "false")
    raw = json.dumps([{"name":"X","min_stock":5,"current_stock":1}])  # no id anywhere
    out = normalize_deficit_payload(raw)
    assert out and out[0]["id"].startswith("SURR-")
    assert out[0]["name"] == out[0]["id"] or out[0]["name"] == "X"

def test_deficit_uuid_hidden_in_other_field():
    raw = json.dumps([{"Номенклатура":{"ref":"c7e8e58f-49b7-11e6-8a7c-0025903e6d16"},"min_stock":2,"current_stock":0}])
    out = normalize_deficit_payload(raw)
    assert _UUID_RE.fullmatch(out[0]["id"])

def test_deficit_kv_text_line():
    raw = 'name=C, min_stock=8, current_stock=1'
    out = normalize_deficit_payload(raw)
    assert out[0]["deficit"] == 7
    assert out[0]["id"].startswith("SURR-")

def test_stock_plain():
    assert normalize_stock('{"stock": 12.5}') == 12.5

def test_stock_xdto_number():
    raw = json.dumps({"#type":"jxs:number","#value": "3"})
    assert normalize_stock(raw) == 3.0