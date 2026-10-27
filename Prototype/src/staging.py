"""Step 2: snapshot every source once, run everything from the snapshot."""
import json, os
from datetime import datetime, timezone
import pandas as pd
from connectors import SourceError
from src.security.validate import validate_frame


def extract_all(connectors: dict, required: list, staging_dir: str, since=None, run_id=None):
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(staging_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    frames, manifest, failures = {}, {}, []
    for name, conn in connectors.items():
        try:
            df = conn.fetch(since)
            df.to_csv(os.path.join(run_dir, f"{name}.csv"), index=False, encoding="utf-8")
            frames[name] = df
            manifest[name] = {"rows": len(df), "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "incremental_since": since}
        except SourceError as e:
            failures.append((name, str(e)))
            manifest[name] = {"error": str(e)}
    failed_required = [n for n, _ in failures if n in required]
    with open(os.path.join(run_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    if failed_required:
        raise SourceError("required source(s) unavailable, run stopped: " + "; ".join(m for _, m in failures))
    return frames, manifest, run_dir


def to_pipeline_frame(frames: dict) -> pd.DataFrame:
    """Standard shape -> pipeline shape (cust_id without prefix, source lower-case)."""
    parts = []
    for name, df in frames.items():
        d = df.rename(columns={"source_id": "cust_id"}).copy()
        d["cust_id"] = d["cust_id"].str.split(":", n=1).str[1]
        d = validate_frame(d[["cust_id", "name", "address", "pin"]])
        d["source"] = name
        parts.append(d)
    return pd.concat(parts, ignore_index=True)
