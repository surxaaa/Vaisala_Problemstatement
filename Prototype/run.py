"""Usage: python run.py [--mock]   (default uses local Ollama)"""
import json, os, sys
from src.logging_setup import setup
from src.pipeline import run
from src.export import safe_export
from src.llm_client import call_ollama, MODEL

def mock(prompt, system):
    return '{"same": false, "confidence": 50, "reason": "mock"}'

if __name__ == "__main__":
    setup()
    llm = mock if "--mock" in sys.argv else call_ollama
    paths = {s: f"data/{s}.csv" for s in ("sap", "crm", "billing")}
    out, rev, rej, summary = run(paths, llm)
    os.makedirs("output", exist_ok=True)
    safe_export(out, "output/golden.xlsx"); safe_export(rev, "output/review.xlsx")
    rej.to_csv("output/rejects.csv", index=False)
    print("model:", "mock" if llm is mock else MODEL)
    print(json.dumps(summary, indent=2))
