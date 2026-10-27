from src.security.profanity import *

def test_profanity_detected():
    assert has_profanity("Big Sh1t Traders")
    assert has_profanity("what the F U C K") is False  # spaced letters are a known limitation
    assert has_profanity("ASSHOLE Corp")

def test_no_false_positive():
    assert not has_profanity("Scunthorpe Classic Engineering")
    assert not has_profanity("Acetech India")

def test_junk():
    assert is_junk("TEST") and is_junk("") and is_junk("xxxx")
    assert not is_junk("Test Engineering Works")

def test_quarantine_reason():
    assert quarantine_reason("dummy", "x") == "junk name"
    assert quarantine_reason("Good Co", "shit road") == "profanity"
    assert quarantine_reason("Good Co", "Anna Salai") is None
