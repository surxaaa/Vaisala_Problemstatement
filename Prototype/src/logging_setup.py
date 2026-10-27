import logging, os
from src.security.pii import mask_pii

class PiiFilter(logging.Filter):
    def filter(self, record):
        record.msg = mask_pii(str(record.msg))
        return True

def setup():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger().addFilter(PiiFilter())

def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")   # never hardcode, never log
    return key
