import re

BLOCKLIST = {"fuck", "shit", "bastard", "bitch", "asshole"}  # extend from a file
JUNK = re.compile(r"^(test|dummy|xxx+|na|n/a|none|null|asdf+|\.+)$", re.I)
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "@": "a", "$": "s"})

def has_profanity(text: str) -> bool:
    words = re.findall(r"[a-z0-9@$]+", (text or "").lower())
    return any(w.translate(LEET) in BLOCKLIST for w in words)

def is_junk(text: str) -> bool:
    t = (text or "").strip()
    return t == "" or bool(JUNK.match(t))

def quarantine_reason(name: str, address: str) -> str | None:
    if is_junk(name):
        return "junk name"
    if has_profanity(name) or has_profanity(address):
        return "profanity"
    return None
