"""Standard connector contract: every system returns the same 5-column shape."""
import pandas as pd

STANDARD_COLS = ["source_system", "source_id", "name", "address", "pin"]


def _to_text(v) -> str:
    if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():             # numeric column + NULLs arrives as float: 600002.0
        return str(int(v))
    return str(v).strip()


class SourceError(Exception):
    """A source could not be read. The run must stop (exit code 4)."""


class SourceConnector:
    def __init__(self, system: str, cfg: dict):
        self.system = system.upper()                 # e.g. SAP
        self.cfg = cfg
        self.id_prefix = cfg.get("id_prefix", self.system)
        self.columns = cfg["columns"]                # standard name -> source column

    def _extract(self, since=None) -> pd.DataFrame:
        raise NotImplementedError

    def fetch(self, since=None) -> pd.DataFrame:
        try:
            raw = self._extract(since)
        except SourceError:
            raise
        except Exception as e:
            raise SourceError(f"{self.system}: {type(e).__name__}") from e   # no payload/credentials in message
        return self._standardize(raw)

    def _standardize(self, raw: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.columns.values() if c not in raw.columns]
        if missing:
            raise SourceError(f"{self.system}: missing source columns {missing}")
        df = pd.DataFrame({std: raw[src] for std, src in self.columns.items()})
        for c in df.columns:                                   # text only; NULL -> ""; CHAR padding removed
            df[c] = df[c].astype(object).map(_to_text)
        df["source_id"] = self.id_prefix + ":" + df["source_id"]   # SAP:1001 never clashes with CRM:1001
        df["source_system"] = self.system
        return df[STANDARD_COLS]
