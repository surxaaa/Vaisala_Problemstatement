"""Option A write-back: only into a separate MDM schema/database that YOU own, and only if MDM_DB_URL is set.
Source tables are never touched. Writes go to *_stg tables, counts are checked, then swapped in one transaction."""
import os
import pandas as pd


def build_mdm_frames(golden: pd.DataFrame) -> dict:
    g = golden.copy()
    g["source_id"] = g["source"].str.upper() + ":" + g["cust_id"]
    frames = {
        "customer_golden": (g.sort_values("source").groupby("golden_id", as_index=False)
                             .agg(canonical_name=("name", "first"), canonical_pin=("pin", "first"),
                                  member_count=("cust_id", "count"))),
        "customer_xref": g[["golden_id", "source_id", "method", "score", "reason", "timestamp"]],
    }
    for s in g["source"].unique():
        frames[f"{s}_customer_clean"] = g[g.source == s][["source_id", "golden_id", "name", "address", "pin"]]
    return frames


def write_mdm(golden: pd.DataFrame, url: str | None = None) -> str:
    url = url or os.environ.get("MDM_DB_URL")
    if not url:
        return "skipped: MDM_DB_URL not set (no database write)"
    from sqlalchemy import create_engine, text
    frames = build_mdm_frames(golden)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        for t, df in frames.items():                             # 1. load staging copies
            df.to_sql(f"{t}_stg", engine, if_exists="replace", index=False)
        with engine.connect() as c:                              # 2. verify counts
            for t, df in frames.items():
                n = c.execute(text(f"SELECT COUNT(*) FROM {t}_stg")).scalar()
                if n != len(df):
                    raise RuntimeError(f"count mismatch on {t}")
        with engine.begin() as c:                                # 3. swap in ONE transaction
            for t, df in frames.items():
                df.head(0).to_sql(t, c, if_exists="append", index=False)   # create if missing
                c.execute(text(f"DELETE FROM {t}"))
                c.execute(text(f"INSERT INTO {t} SELECT * FROM {t}_stg"))
                c.execute(text(f"DROP TABLE {t}_stg"))
        return f"written: {', '.join(frames)}"
    finally:
        engine.dispose()
