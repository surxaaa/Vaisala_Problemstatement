import pandas as pd
from src.pipeline import run_frame, pair_scores, golden_id_for, build_clusters, MIN_PAIR
from src.standardize import standardize_address, standardize_name, standardize_pin
from src.evaluate import evaluate

NOW = "2026-01-01T00:00:00+00:00"
def llm_down(p, s=None): raise TimeoutError()
def llm_yes(p, s=None): return '{"same": true, "confidence": 95, "reason": "x"}'

def frame(rows):
    df = pd.DataFrame(rows, columns=["source", "cust_id", "name", "address", "pin"])
    df["pin_raw"] = df["pin"]
    return df

# ---------- change 1: combined score, second signal ----------

def rec(name, addr, pin):
    return {"name_std": standardize_name(name), "address_std": standardize_address(addr), "pin": pin}

def test_missing_pin_is_reweighted_not_penalised():
    s = pair_scores(rec("Acetech India", "12 Anna Salai", ""), rec("Acetech India", "12 Anna Salai", ""))
    assert s["pin"] is None and s["combined"] == 100 and s["second_signal"]

def test_name_only_pair_has_no_second_signal():
    s = pair_scores(rec("Acetech India", "", ""), rec("Acetech India", "", ""))
    assert s["name"] == 100 and not s["second_signal"]

def test_same_name_different_cities_never_auto_match():
    df = frame([("sap", "1", "Acetech India Pvt Ltd", "Anna Salai Chennai", ""),
                ("crm", "2", "Acetech India Private Limited", "Whitefield Bengaluru", "")])
    out, rev, *_ = run_frame(df, llm_down, NOW)           # LLM unavailable: cannot fall back on it
    assert out.golden_id.nunique() == 2 and len(rev) == 1

def test_same_name_same_address_missing_pin_auto_matches():
    df = frame([("sap", "1", "Acetech India Pvt Ltd", "12 Anna Salai Chennai", ""),
                ("crm", "2", "Acetech India Private Limited", "12 Anna Salai, Chennai", "")])
    out, *_ = run_frame(df, llm_down, NOW)
    assert out.golden_id.nunique() == 1 and (out.method == "fuzzy").any()

def test_conflicting_pins_block_auto_match():
    df = frame([("sap", "1", "Ganesh Traders", "10 Market St", "625001"),
                ("crm", "2", "Ganesh Traders", "10 Market St", "636001")])
    out, rev, *_ = run_frame(df, llm_down, NOW)
    assert out.golden_id.nunique() == 2

def test_cohesion_uses_combined_score():
    scores = {("A", "B"): 95, ("B", "C"): 95, ("A", "C"): MIN_PAIR - 1}
    clusters, flagged = build_clusters(["A", "B", "C"], [("A", "B"), ("B", "C")],
                                       lambda a, b: scores[(min(a, b), max(a, b))])
    assert clusters == [["A"], ["B"], ["C"]] and flagged == [("A", "C")]

# ---------- change 2: stable golden ids ----------

def test_golden_id_format_and_determinism():
    gid = golden_id_for("SAP:1001")
    assert gid == golden_id_for("SAP:1001") and gid.startswith("G") and len(gid) == 11

def test_golden_id_stable_when_unrelated_rows_added_and_order_changes():
    base = [("sap", "1001", "Acetech India Pvt Ltd", "12 Anna Salai Chennai", "600002"),
            ("crm", "C-884", "Acetech India Private Limited", "12 Anna Salai Chennai", "600002")]
    extra = base + [("billing", "B_9", "Zenith Castings", "Salem", "636001")]
    a, *_ = run_frame(frame(base), llm_down, NOW)
    b, *_ = run_frame(frame(list(reversed(extra))), llm_down, NOW)
    ida = a[a.cust_id == "1001"].golden_id.iloc[0]
    idb = b[b.cust_id == "1001"].golden_id.iloc[0]
    assert ida == idb == golden_id_for("CRM:C-884")   # lowest key in the group sorts CRM before SAP

# ---------- change 3: address / pin standardization ----------

def test_address_standardization():
    assert standardize_address("12, Anna Salai Rd.") == "12 anna salai road"
    assert standardize_address("45 Avinashi ROAD  Coimbatore 641018") == "45 avinashi road coimbatore"
    assert standardize_address("3 Mill St, Ind. Est 600 002") == "3 mill street industrial estate"
    assert standardize_address(None) == ""
    assert standardize_pin("600 002") == "600002"

def test_std_columns_written_next_to_raw():
    df = frame([("sap", "1", "ACME Pvt. Ltd.", "5 Mill Rd.", "600 002")])
    df["pin"] = "600002"; df["pin_raw"] = "600 002"
    out, *_ = run_frame(df, llm_down, NOW)
    r = out.iloc[0]
    assert (r["name"], r["address"], r["pin"]) == ("ACME Pvt. Ltd.", "5 Mill Rd.", "600 002")
    assert (r["name_std"], r["address_std"], r["pin_std"]) == ("acme", "5 mill road", "600002")

# ---------- change 4: measured accuracy ----------

def golden(rows):
    return pd.DataFrame(rows, columns=["golden_id", "source", "cust_id"])

TRUTH = pd.DataFrame({"source_id": ["SAP:1", "CRM:2", "BILLING:3", "SAP:4"],
                      "true_cluster": ["A", "A", "A", "B"]})
NO_REVIEW = pd.DataFrame(columns=["key_a", "key_b"])

def test_perfect_result():
    g = golden([("G1", "sap", "1"), ("G1", "crm", "2"), ("G1", "billing", "3"), ("G2", "sap", "4")])
    m = evaluate(g, NO_REVIEW, TRUTH)
    assert (m["precision"], m["recall"], m["f1"], m["false_merges"], m["missed_merges"]) == (1.0, 1.0, 1.0, 0, 0)

def test_false_merge_counted_and_listed():
    g = golden([("G1", "sap", "1"), ("G1", "crm", "2"), ("G1", "billing", "3"), ("G1", "sap", "4")])
    m = evaluate(g, NO_REVIEW, TRUTH)
    assert m["false_merges"] == 3 and m["precision"] == 0.5 and m["recall"] == 1.0
    assert "SAP:1 ~ SAP:4" in m["false_merge_pairs"]

def test_missed_merge_and_review_queue_credit():
    g = golden([("G1", "sap", "1"), ("G1", "crm", "2"), ("G3", "billing", "3"), ("G2", "sap", "4")])
    rev = pd.DataFrame({"key_a": ["BILLING:3"], "key_b": ["SAP:1"]})
    m = evaluate(g, rev, TRUTH)
    assert m["missed_merges"] == 2 and m["recall"] == round(1 / 3, 4)
    assert m["false_merges"] == 0 and m["precision"] == 1.0 and m["missed_but_in_review_queue"] == 1

def test_rejected_rows_are_not_evaluated():
    g = golden([("G1", "sap", "1"), ("G1", "crm", "2")])         # rows 3 and 4 were rejected
    m = evaluate(g, NO_REVIEW, TRUTH)
    assert m["records_evaluated"] == 2 and m["false_merges"] == 0

def test_demo_data_never_creates_false_merges_without_llm():
    from src.pipeline import run
    out, rev, *_ = run({s: f"data/{s}.csv" for s in ("sap", "crm", "billing")}, llm_down, NOW)
    m = evaluate(out, rev, pd.read_csv("data/truth.csv", dtype=str))
    assert m["false_merges"] == 0 and m["precision"] == 1.0

def test_llm_yes_cannot_merge_same_name_in_different_cities():
    df = frame([("sap", "1", "Ganesh Traders", "10 Market St Madurai", "625001"),
                ("crm", "2", "Ganesh Traders", "4 Fort Rd Salem", "636001")])
    out, rev, *_ = run_frame(df, llm_yes, NOW)          # model says "same, 95% sure"
    assert out.golden_id.nunique() == 2 and "pin and name disagree" in " ".join(rev.reason)
