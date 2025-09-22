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