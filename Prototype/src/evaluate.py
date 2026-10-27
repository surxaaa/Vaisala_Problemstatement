"""Measured accuracy against a hand-labelled truth file (columns: source_id, true_cluster)."""
from itertools import combinations
import pandas as pd


def _pairs(groups: dict) -> set:
    out = set()
    for members in groups.values():
        out.update(frozenset(p) for p in combinations(sorted(members), 2))
    return out


def evaluate(golden: pd.DataFrame, review: pd.DataFrame, truth: pd.DataFrame) -> dict:
    g = golden.copy()
    g["source_id"] = g["source"].str.upper() + ":" + g["cust_id"]
    t = truth.set_index("source_id")["true_cluster"].to_dict()
    g = g[g.source_id.isin(t)]                       # rejected rows are not evaluated
    pred_groups, true_groups = {}, {}
    for sid, gid in zip(g.source_id, g.golden_id):
        pred_groups.setdefault(gid, []).append(sid)
        true_groups.setdefault(t[sid], []).append(sid)
    pred, true = _pairs(pred_groups), _pairs(true_groups)
    tp, false_merges, missed = pred & true, pred - true, true - pred
    precision = len(tp) / len(pred) if pred else None
    recall = len(tp) / len(true) if true else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else (0.0 if pred or true else None)
    review_pairs = {frozenset((a, b)) for a, b in zip(review.key_a, review.key_b)} if len(review) else set()
    fmt = lambda ps: sorted(" ~ ".join(sorted(p)) for p in ps)
    return {
        "records_evaluated": len(g), "true_match_pairs": len(true), "predicted_match_pairs": len(pred),
        "precision": None if precision is None else round(precision, 4),
        "recall": None if recall is None else round(recall, 4),
        "f1": None if f1 is None else round(f1, 4),
        "false_merges": len(false_merges), "false_merge_pairs": fmt(false_merges),
        "missed_merges": len(missed), "missed_merge_pairs": fmt(missed),
        "missed_but_in_review_queue": len(missed & review_pairs),
    }
