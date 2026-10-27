import pandas as pd, pytest
from src.security.validate import *

def test_pin_normalized():
    assert normalize_pin("600 002") == "600002"
    assert normalize_pin("60002") == ""
    assert normalize_pin(None) == ""

def test_control_chars_and_length():
    assert clean_text("Ace\x00tech\n  India") == "Acetech India"
    assert len(clean_text("a" * 1000)) == MAX_FIELD_LEN

def test_missing_columns_rejected():
    with pytest.raises(ValidationError):
        validate_frame(pd.DataFrame({"name": ["x"]}))

def test_extra_columns_dropped():
    df = pd.DataFrame({"cust_id": ["1"], "name": ["A"], "address": ["B"],
                       "pin": ["600002"], "secret": ["zzz"]})
    assert "secret" not in validate_frame(df).columns
