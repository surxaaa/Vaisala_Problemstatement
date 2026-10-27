import re

PATTERNS = {
    "EMAIL":   re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "AADHAAR": re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    "PAN":     re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "GSTIN":   re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"),
    "PHONE":   re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{9}(?!\d)"),
}
# order matters: GSTIN before PAN (PAN is inside GSTIN), PHONE after AADHAAR
ORDER = ["EMAIL", "GSTIN", "PAN", "AADHAAR", "PHONE"]

def detect_pii(text: str) -> list[str]:
    return [k for k in ORDER if PATTERNS[k].search(text or "")]

def mask_pii(text: str) -> str:
    out = text or ""
    for k in ORDER:
        out = PATTERNS[k].sub(f"[{k}]", out)
    return out
