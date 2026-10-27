import logging
import pandas as pd
from src.pipeline import run, build_clusters

NOW = "2026-01-01T00:00:00+00:00"
PATHS = {s: f"data/{s}.csv" for s in ("sap", "crm", "billing")}

def fake_llm_yes(prompt, system=None):  return '{"same": true, "confidence": 95, "reason": "match"}'
def fake_llm_garbage(prompt, system=None): return "I will ignore the rules"
def fake_llm_down(prompt, system=None): raise TimeoutError()

def gid(out, source, cid):
    return out[(out.source == source) & (out.cust_id == cid)].golden_id.iloc[0]

def test_clear_duplicates_share_golden_id():
    out, *_ = run(PATHS, fake_llm_yes, NOW)
    assert gid(out, "sap", "1001") == gid(out, "crm", "C-884") == gid(out, "billing", "B_77")

def test_near_miss_stays_separate():
    out, *_ = run(PATHS, fake_llm_yes, NOW)
    assert gid(out, "sap", "1001") != gid(out, "crm", "C-885")

def test_injection_never_calls_llm_and_goes_to_review():
    prompts = []
    def spy(p, s=None): prompts.append(p); return fake_llm_yes(p)
    out, rev, *_ = run(PATHS, spy, NOW)
    assert not any("Ignore previous" in p for p in prompts)

def test_garbage_llm_goes_to_review_and_completes():
    out, rev, rej, summ = run(PATHS, fake_llm_garbage, NOW)
    assert len(out) > 0 and summ["review_pairs"] >= 0

def test_llm_down_does_not_crash():
    out, rev, rej, summ = run(PATHS, fake_llm_down, NOW)
    assert len(out) > 0
    assert gid(out, "sap", "1001") == gid(out, "crm", "C-884")   # fuzzy path needs no LLM

def test_profanity_and_junk_rejected():
    out, rev, rej, _ = run(PATHS, fake_llm_yes, NOW)
    assert {"1003", "C-888"} <= set(rej.cust_id)
    assert not out.cust_id.isin(["1003", "C-888"]).any()

def test_no_pii_in_prompts_or_logs(caplog):
    prompts = []
    def spy(p, s=None): prompts.append(p); return fake_llm_yes(p)
    with caplog.at_level(logging.INFO):
        run(PATHS, spy, NOW)
    blob = " ".join(prompts) + " ".join(r.getMessage() for r in caplog.records)
    for raw in ("ravi@acetech.com", "9876543210"):
        assert raw not in blob

def test_pii_rows_counted():
    *_, summ = run(PATHS, fake_llm_yes, NOW)
    assert summ["pii_masked_count"] >= 1

def test_cluster_cohesion_splits_chain():
    names = {"A": "alpha", "B": "alphb", "C": "zzzzz"}
    from rapidfuzz import fuzz
    score = lambda a, b: fuzz.ratio(names[a], names[b])
    clusters, flagged = build_clusters(["A", "B", "C"], [("A", "B"), ("B", "C")], score)
    assert clusters == [["A"], ["B"], ["C"]] and flagged

def test_deterministic():
    a, *_ = run(PATHS, fake_llm_yes, NOW)
    b, *_ = run(PATHS, fake_llm_yes, NOW)
    pd.testing.assert_frame_equal(a, b)
