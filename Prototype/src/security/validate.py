import re
import pandas as pd

ALLOWED_COLS = ("cust_id", "name", "address", "pin")
MAX_ROWS = 100_000
MAX_FIELD_LEN = 300
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

class ValidationError(Exception):
    pass

def clean_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = CONTROL_CHARS.sub("", str(value)).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:MAX_FIELD_LEN]

def normalize_pin(value) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 6 else ""   # empty means missing or invalid

def validate_frame(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) > MAX_ROWS:
        raise ValidationError(f"Too many rows: {len(df)}")
    missing = set(ALLOWED_COLS) - set(df.columns)
    if missing:
        raise ValidationError(f"Missing columns: {missing}")
    df = df[list(ALLOWED_COLS)].copy()          # drop unexpected columns
    for c in ("cust_id", "name", "address"):
        df[c] = df[c].map(clean_text)
    df["pin_raw"] = df["pin"].map(clean_text)
    df["pin"] = df["pin"].map(normalize_pin)
    return df[df["cust_id"] != ""]
