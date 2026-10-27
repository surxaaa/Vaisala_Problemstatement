import re
from src.security.validate import normalize_pin

SUFFIXES = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "company", "corp", "the"}

ADDRESS_ABBREV = {
    "rd": "road", "st": "street", "ave": "avenue", "av": "avenue", "hwy": "highway",
    "ste": "suite", "blk": "block", "opp": "opposite", "nr": "near", "ind": "industrial",
    "indl": "industrial", "est": "estate", "bldg": "building", "flr": "floor",
    "mn": "main", "ln": "lane", "cr": "cross", "sq": "square", "pl": "place",
}


def standardize_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " and "))
    return " ".join(w for w in s.split() if w not in SUFFIXES)


def standardize_address(address: str) -> str:
    s = (address or "").lower()
    s = re.sub(r"\b\d{3} ?\d{3}\b", " ", s)                 # pin code text is stored separately
    s = re.sub(r"[^a-z0-9 ]", " ", s)                       # punctuation -> space
    return " ".join(ADDRESS_ABBREV.get(w, w) for w in s.split())


def standardize_pin(pin) -> str:
    return normalize_pin(pin)
