import time, logging
log = logging.getLogger("pipeline")

class CircuitOpen(Exception):
    pass

class CircuitBreaker:
    def __init__(self, max_failures=5, reset_after=60):
        self.max_failures, self.reset_after = max_failures, reset_after
        self.failures, self.opened_at = 0, None

    def call(self, fn, *a, **kw):
        if self.opened_at and time.time() - self.opened_at < self.reset_after:
            raise CircuitOpen("LLM circuit open")
        if self.opened_at:                      # half-open: allow one trial
            self.opened_at, self.failures = None, 0
        try:
            result = fn(*a, **kw)
            self.failures = 0
            return result
        except Exception:
            self.failures += 1
            if self.failures >= self.max_failures:
                self.opened_at = time.time()
            raise

def with_retry(fn, attempts=3, base_delay=0.5, sleep=time.sleep):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except CircuitOpen:
            raise
        except Exception as e:
            last = e
            log.warning("attempt %d failed: %s", i + 1, type(e).__name__)  # no payload in logs
            if i < attempts - 1:
                sleep(base_delay * (2 ** i))
    raise last

def safe_llm_decision(call_llm, prompt, breaker):
    """Never raises: any failure becomes a manual-review result."""
    try:
        raw = breaker.call(lambda: with_retry(lambda: call_llm(prompt)))
        return raw, None
    except Exception as e:
        return None, f"llm_unavailable:{type(e).__name__}"
