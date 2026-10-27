"""Usage: python run.py [--config config/connectors.yaml] [--mock] [--since 2026-01-01]
Exit codes: 0 ok, 4 a required source could not be read."""
import argparse, json, os, sys
from datetime import datetime, timezone
from connectors import load_config, build_connectors, SourceError
from src.logging_setup import setup
from src.staging import extract_all, to_pipeline_frame
from src.pipeline import run_frame
from src.export import safe_export
from src.mdm_writer import write_mdm
from src.llm_client import call_ollama, MODEL

def mock(prompt, system):
    return '{"same": false, "confidence": 50, "reason": "mock"}'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/connectors.yaml")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--since", default=None)
    a = ap.parse_args()
    setup()
    cfg = load_config(a.config)
    try:
        frames, manifest, run_dir = extract_all(build_connectors(cfg), cfg["required"], cfg["staging_dir"], a.since)
    except SourceError as e:
        print("ERROR:", e, file=sys.stderr)
        return 4
    llm = mock if a.mock else call_ollama
    out, rev, rej, summary = run_frame(to_pipeline_frame(frames), llm)
    os.makedirs("output", exist_ok=True)
    safe_export(out, "output/golden.xlsx"); safe_export(rev, "output/review.xlsx")
    rej.to_csv("output/rejects.csv", index=False)
    mdm = write_mdm(out)
    report = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "model": "mock" if a.mock else MODEL, "staging_snapshot": run_dir,
              "sources": manifest, "summary": summary, "mdm_write": mdm}
    json.dump(report, open("output/run_report.json", "w"), indent=2)
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
