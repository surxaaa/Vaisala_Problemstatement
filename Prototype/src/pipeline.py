import hashlib, logging
from datetime import datetime, timezone
import pandas as pd
from rapidfuzz import fuzz

from src.standardize import standardize_name, standardize_address
from src.security.validate import validate_frame
from src.security.pii import detect_pii
from src.security.profanity import quarantine_reason
from src.security.llm_guard import (SYSTEM_PROMPT, looks_like_injection, build_prompt,
                                    parse_verdict, apply_guardrails)
from src.resilience import CircuitBreaker, safe_llm_decision

log = logging.getLogger("pipeline")

# --- thresholds ---
BORDERLINE = 70            # name score below this: not a candidate pair
AUTO_NAME = 92             # auto-match needs name score at least this ...
AUTO_COMBINED = 90         # ... AND combined score at least this ...
ADDR_SIGNAL = 80           # ... AND a second signal: pin match OR address score at least this
MIN_PAIR = 70              # cluster cohesion: every pair in a group needs this combined score
WEIGHTS = {"name": 0.5, "address": 0.3, "pin": 0.2}


def pair_scores(ra: dict, rb: dict) -> dict:
    """Name / address / pin scores plus a combined score re-weighted over the fields that exist on both sides."""
    name = fuzz.token_sort_ratio(ra["name_std"], rb["name_std"])
    parts = {"name": (name, WEIGHTS["name"])}
    addr = None
    if ra["address_std"] and rb["address_std"]:
        addr = fuzz.token_sort_ratio(ra["address_std"], rb["address_std"])
        parts["address"] = (addr, WEIGHTS["address"])
    pin = None
    if ra["pin"] and rb["pin"]:
        pin = 100.0 if ra["pin"] == rb["pin"] else 0.0
        parts["pin"] = (pin, WEIGHTS["pin"])
    total_w = sum(w for _, w in parts.values())
    combined = sum(v * w for v, w in parts.values()) / total_w
    second_signal = (pin == 100.0) or (addr is not None and addr >= ADDR_SIGNAL)
    return {"name": name, "address": addr, "pin": pin, "combined": combined, "second_signal": second_signal}


def golden_id_for(lowest_key: str) -> str:
    """Stable across runs: derived from the lowest member key, e.g. SAP:1001."""
    return "G" + hashlib.sha256(lowest_key.encode()).hexdigest()[:10]


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
            r["key"] = f'{r["source"].upper()}:{r["cust_id"]}'
            r["name_std"] = standardize_name(r["name"])
            r["address_std"] = standardize_address(r["address"])
            r.setdefault("pin_raw", r["pin"])
            keep.append(r)
        except Exception as e:
            rejects.append({"source": r.get("source"), "cust_id": r.get("cust_id"), "reason": type(e).__name__})
    rec = {r["key"]: r for r in keep}
    keys = sorted(rec)
    _cache = {}
    def scores(a, b):
        if (a, b) not in _cache:
            _cache[(a, b)] = pair_scores(rec[a], rec[b])
        return _cache[(a, b)]
    combined = lambda a, b: scores(min(a, b), max(a, b))["combined"]

    edges, audit, review, llm_cache = [], {}, [], {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ra, rb = rec[a], rec[b]
            if ra["source"] == rb["source"]:
                continue
            try:
                sc = scores(a, b)
                s = sc["name"]
                if s < BORDERLINE:
                    continue
                if s >= AUTO_NAME and sc["combined"] >= AUTO_COMBINED and sc["second_signal"]:
                    edges.append((a, b)); audit[(a, b)] = ("fuzzy", sc["combined"], "name+address/pin agree"); continue
                if looks_like_injection(ra["name"], rb["name"], ra["address"], rb["address"]):
                    review.append((a, b, s, sc["combined"], "injection pattern, LLM skipped")); continue
                prompt = build_prompt(ra, rb)
                h = hashlib.sha256(prompt.encode()).hexdigest()
                if h not in llm_cache:
                    llm_cache[h] = safe_llm_decision(lambda p: call_llm(p, SYSTEM_PROMPT), prompt, breaker)
                raw, err = llm_cache[h]
                if err:
                    review.append((a, b, s, sc["combined"], err)); continue
                verdict, conf, reason = apply_guardrails(parse_verdict(raw), sc["combined"], ra["pin"], rb["pin"])   # combined, not name-only
                if verdict == "MATCH":
                    edges.append((a, b)); audit[(a, b)] = ("llm", conf, reason)
                elif verdict == "REVIEW":
                    review.append((a, b, s, sc["combined"], reason))
                log.info("pair %s %s name=%.0f combined=%.0f verdict=%s", a, b, s, sc["combined"], verdict)
            except Exception as e:
                rejects.append({"source": "pair", "cust_id": f"{a}|{b}", "reason": type(e).__name__})
    clusters, flagged = build_clusters(keys, edges, combined)
    for a, b in flagged:
        review.append((a, b, scores(a, b)["name"], scores(a, b)["combined"], "cluster cohesion failed"))
    rows, seen = [], {}
    for members in clusters:
        gid = golden_id_for(members[0])
        if gid in seen:
            raise RuntimeError(f"golden id collision: {gid}")
        seen[gid] = members[0]
        for k in members:
            r = rec[k]
            m = [audit[e] for e in audit if k in e and e[0] in members and e[1] in members]
            method, sc_, reason = (m[0] if m else ("none", 0, "singleton"))
            rows.append({"golden_id": gid, "source": r["source"], "cust_id": r["cust_id"],
                         "name": r["name"], "address": r["address"], "pin": r["pin_raw"],
                         "name_std": r["name_std"], "address_std": r["address_std"], "pin_std": r["pin"],
                         "method": method, "score": round(float(sc_), 1), "reason": reason, "timestamp": now})
    out = pd.DataFrame(rows)
    rev = pd.DataFrame(review, columns=["key_a", "key_b", "name_score", "combined_score", "reason"])
    rej = pd.DataFrame(rejects, columns=["source", "cust_id", "reason"])
    summary = {"rows_in": len(df), "rows_kept": len(keep), "rejected": len(rej),
               "golden_records": len(clusters), "review_pairs": len(rev), "pii_masked_count": pii_count}
    return out, rev, rej, summary


def run(paths: dict, call_llm, now: str | None = None, breaker=None):
    """Convenience wrapper: CSV files (cust_id,name,address,pin) keyed by source name."""
    df, _ = load_sources(paths)
    return run_frame(df, call_llm, now, breaker)
