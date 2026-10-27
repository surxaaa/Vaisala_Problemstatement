import hashlib, logging
from datetime import datetime, timezone
import pandas as pd
from rapidfuzz import fuzz

from src.standardize import standardize_name
from src.security.validate import validate_frame
from src.security.pii import detect_pii
from src.security.profanity import quarantine_reason
from src.security.llm_guard import (SYSTEM_PROMPT, looks_like_injection, build_prompt,
                                    parse_verdict, apply_guardrails)
from src.resilience import CircuitBreaker, safe_llm_decision

log = logging.getLogger("pipeline")
AUTO_MATCH, BORDERLINE, MIN_PAIR = 92, 70, 75


def load_sources(paths: dict) -> tuple[pd.DataFrame, list]:
    frames, rejects = [], []
    for source, path in paths.items():
        df = validate_frame(pd.read_csv(path, dtype=str, keep_default_na=False))
        df["source"] = source
        frames.append(df)
    return pd.concat(frames, ignore_index=True), rejects


def build_clusters(keys, match_edges, score_fn, min_pair=MIN_PAIR):
    """Union-find over MATCH edges, then cohesion check. Returns (clusters, flagged_pairs)."""
    parent = {k: k for k in keys}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in match_edges:
        parent[find(a)] = find(b)
    groups = {}
    for k in keys:
        groups.setdefault(find(k), []).append(k)
    clusters, flagged = [], []
    for members in groups.values():
        members.sort()
        bad = [(a, b) for i, a in enumerate(members) for b in members[i + 1:] if score_fn(a, b) < min_pair]
        if bad:
            flagged.extend(bad)
            clusters.extend([m] for m in members)      # split: do not merge
        else:
            clusters.append(members)
    return sorted(clusters), flagged


def run_frame(df: pd.DataFrame, call_llm, now: str | None = None, breaker=None):
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    breaker = breaker or CircuitBreaker()
    rejects, keep = [], []
    pii_count = 0
    for r in df.to_dict("records"):
        try:
            why = quarantine_reason(r["name"], r["address"])
            if why:
                rejects.append({"source": r["source"], "cust_id": r["cust_id"], "reason": why}); continue
            if detect_pii(r["name"]) or detect_pii(r["address"]):
                pii_count += 1
            r["key"] = f'{r["source"]}:{r["cust_id"]}'
            r["std"] = standardize_name(r["name"])
            keep.append(r)
        except Exception as e:
            rejects.append({"source": r.get("source"), "cust_id": r.get("cust_id"), "reason": type(e).__name__})
    rec = {r["key"]: r for r in keep}
    keys = sorted(rec)
    score = lambda a, b: fuzz.token_sort_ratio(rec[a]["std"], rec[b]["std"])

    edges, audit, review, cache = [], {}, [], {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ra, rb = rec[a], rec[b]
            if ra["source"] == rb["source"]:
                continue
            try:
                s = score(a, b)
                if s < BORDERLINE:
                    continue
                pins_differ = ra["pin"] and rb["pin"] and ra["pin"] != rb["pin"]
                if s >= AUTO_MATCH and not pins_differ:
                    edges.append((a, b)); audit[(a, b)] = ("fuzzy", s, "high name score, pin ok"); continue
                if looks_like_injection(ra["name"], rb["name"], ra["address"], rb["address"]):
                    review.append((a, b, s, "injection pattern, LLM skipped")); continue
                prompt = build_prompt(ra, rb)
                h = hashlib.sha256(prompt.encode()).hexdigest()
                if h not in cache:
                    cache[h] = safe_llm_decision(lambda p: call_llm(p, SYSTEM_PROMPT), prompt, breaker)
                raw, err = cache[h]
                if err:
                    review.append((a, b, s, err)); continue
                verdict, conf, reason = apply_guardrails(parse_verdict(raw), s, ra["pin"], rb["pin"])
                if verdict == "MATCH":
                    edges.append((a, b)); audit[(a, b)] = ("llm", conf, reason)
                elif verdict == "REVIEW":
                    review.append((a, b, s, reason))
                log.info("pair %s %s score=%.0f verdict=%s", a, b, s, verdict)
            except Exception as e:
                rejects.append({"source": "pair", "cust_id": f"{a}|{b}", "reason": type(e).__name__})
    clusters, flagged = build_clusters(keys, edges, score)
    for a, b in flagged:
        review.append((a, b, score(a, b), "cluster cohesion failed"))
    rows = []
    for n, members in enumerate(clusters, 1):
        for k in members:
            r = rec[k]
            m = [audit[e] for e in audit if k in e and e[0] in members and e[1] in members]
            method, sc, reason = (m[0] if m else ("none", 0, "singleton"))
            rows.append({"golden_id": f"G{n:05d}", "source": r["source"], "cust_id": r["cust_id"],
                         "name": r["name"], "address": r["address"], "pin": r["pin"],
                         "method": method, "score": round(float(sc), 1), "reason": reason, "timestamp": now})
    out = pd.DataFrame(rows)
    rev = pd.DataFrame(review, columns=["key_a", "key_b", "name_score", "reason"])
    rej = pd.DataFrame(rejects, columns=["source", "cust_id", "reason"])
    summary = {"rows_in": len(df), "rows_kept": len(keep), "rejected": len(rej),
               "golden_records": len(clusters), "review_pairs": len(rev), "pii_masked_count": pii_count}
    return out, rev, rej, summary


def run(paths: dict, call_llm, now: str | None = None, breaker=None):
    """Convenience wrapper: CSV files (cust_id,name,address,pin) keyed by source name."""
    df, _ = load_sources(paths)
    return run_frame(df, call_llm, now, breaker)
