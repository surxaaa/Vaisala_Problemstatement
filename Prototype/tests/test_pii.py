from src.security.pii import *

def test_email_masked():
    assert mask_pii("mail ravi@acetech.com now") == "mail [EMAIL] now"

def test_phone_masked():
    assert "[PHONE]" in mask_pii("call +91 9876543210")

def test_pan_and_gstin():
    assert mask_pii("PAN ABCDE1234F") == "PAN [PAN]"
    assert mask_pii("33ABCDE1234F1Z5") == "[GSTIN]"

def test_aadhaar():
    assert mask_pii("1234 5678 9012") == "[AADHAAR]"

def test_pin_not_masked():
    assert mask_pii("Chennai 600002") == "Chennai 600002"

def test_none_safe():
    assert mask_pii(None) == ""
    assert detect_pii("") == []
