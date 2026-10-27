import pytest
from src.resilience import *

def test_retry_then_success():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3: raise RuntimeError("x")
        return "ok"
    assert with_retry(flaky, sleep=lambda s: None) == "ok"

def test_retry_exhausted_raises():
    with pytest.raises(RuntimeError):
        with_retry(lambda: (_ for _ in ()).throw(RuntimeError("x")), attempts=2, sleep=lambda s: None)

def test_circuit_opens_after_failures():
    b = CircuitBreaker(max_failures=2, reset_after=999)
    def bad(): raise RuntimeError("x")
    for _ in range(2):
        with pytest.raises(RuntimeError): b.call(bad)
    with pytest.raises(CircuitOpen): b.call(lambda: 1)

def test_safe_decision_never_raises():
    b = CircuitBreaker()
    raw, err = safe_llm_decision(lambda p: (_ for _ in ()).throw(TimeoutError()), "p", b)
    assert raw is None and err.startswith("llm_unavailable")
