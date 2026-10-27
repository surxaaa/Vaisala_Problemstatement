"""Generic read-only SQL source. Query and column mapping live in config, not code."""
import os
import pandas as pd
from connectors.base import SourceConnector, SourceError
from src.resilience import with_retry


class SqlConnector(SourceConnector):
    def _engine(self):
        from sqlalchemy import create_engine          # imported lazily: only needed for SQL sources
        env = self.cfg["url_env"]
        url = os.environ.get(env)
        if not url:
            raise SourceError(f"{self.system}: environment variable {env} is not set")
        return create_engine(
            url, pool_pre_ping=True, pool_size=2, pool_recycle=1800,
            connect_args=self.cfg.get("connect_args", {}),   # e.g. {"connect_timeout": 10}
        )

    def _extract(self, since=None) -> pd.DataFrame:
        from sqlalchemy import text
        query = self.cfg["query"]                     # explicit column list, never SELECT *
        params = {"since": since} if ":since" in query and since else {}
        if ":since" in query and not since:
            query = self.cfg.get("full_query", query.split(" WHERE ")[0])   # full refresh fallback
        engine = self._engine()
        try:
            def go():
                with engine.connect() as conn:       # use a read-only DB user
                    return pd.read_sql(text(query), conn, params=params)
            return with_retry(go, attempts=3, base_delay=1.0)
        finally:
            engine.dispose()
