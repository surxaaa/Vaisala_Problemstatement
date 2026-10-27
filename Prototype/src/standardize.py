import re

SUFFIXES = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "company", "corp", "the"}

def standardize_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    return " ".join(w for w in s.split() if w not in SUFFIXES)
