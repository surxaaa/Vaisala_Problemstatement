import pandas as pd
from connectors.base import SourceConnector


class CsvConnector(SourceConnector):
    """File-backed source. Used for the demo and for systems that only give exports."""
    def _extract(self, since=None):
        return pd.read_csv(self.cfg["path"], dtype=str, keep_default_na=False, encoding="utf-8")
