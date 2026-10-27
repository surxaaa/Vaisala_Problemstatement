from src.export import neutralize

def test_formula_neutralized():
    assert neutralize("=HYPERLINK(\"http://evil\")").startswith("'")
    assert neutralize("@SUM(A1)").startswith("'")
    assert neutralize("+91 98765") .startswith("'")

def test_normal_text_unchanged():
    assert neutralize("Acetech India") == "Acetech India"
    assert neutralize(None) == ""
