"""Database connection tests with mocks only: no real database, driver or network is used."""
from unittest.mock import MagicMock
import pandas as pd, pytest
import connectors.sql as sqlmod
from connectors.sql import SqlConnector
from connectors.base import SourceError
from src import mdm_writer
from src.resilience import with_retry as real_retry

COLS = {"source_id": "id", "name": "n", "address": "a", "pin": "p"}
RAW = pd.DataFrame({"id": ["7"], "n": ["Acme   "], "a": ["Road"], "p": ["600002"]})


def make(monkeypatch, **cfg):
    base = {"columns": COLS, "url_env": "FAKE_URL", "query": "SELECT id,n,a,p FROM t"}
    base.update(cfg)
    monkeypatch.setenv("FAKE_URL", "fake://user:SECRET@host/db")
    monkeypatch.setattr(sqlmod, "with_retry",                   # same retry logic, no waiting
                        lambda fn, attempts=3, base_delay=1.0: real_retry(fn, attempts=attempts, base_delay=0))
    engine = MagicMock()
    created = MagicMock(return_value=engine)
    monkeypatch.setattr("sqlalchemy.create_engine", created)
    return SqlConnector("crm", base), engine, created


def test_engine_gets_url_timeouts_and_is_disposed(monkeypatch):
    c, engine, created = make(monkeypatch, connect_args={"connect_timeout": 10})
    monkeypatch.setattr(sqlmod.pd, "read_sql", lambda *a, **k: RAW)
    df = c.fetch()
    kw = created.call_args.kwargs
    assert created.call_args.args[0].startswith("fake://") and kw["connect_args"] == {"connect_timeout": 10}
    assert kw["pool_pre_ping"] is True
    engine.dispose.assert_called_once()
    assert df.source_id[0] == "CRM:7" and df.name[0] == "Acme"


def test_transient_failure_is_retried_then_succeeds(monkeypatch):
    c, engine, _ = make(monkeypatch)
    calls = {"n": 0}
    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3: raise ConnectionError("blip")
        return RAW
    monkeypatch.setattr(sqlmod.pd, "read_sql", flaky)
    assert len(c.fetch()) == 1 and calls["n"] == 3


def test_permanent_failure_becomes_source_error_without_secret(monkeypatch):
    c, engine, _ = make(monkeypatch)
    def boom(*a, **k): raise ConnectionError("login failed for SECRET")
    monkeypatch.setattr(sqlmod.pd, "read_sql", boom)
    with pytest.raises(SourceError) as e:
        c.fetch()
    assert "ConnectionError" in str(e.value) and "SECRET" not in str(e.value)
    engine.dispose.assert_called_once()                        # connection released even on failure


def test_engine_creation_failure_is_source_error(monkeypatch):
    c, engine, created = make(monkeypatch)
    created.side_effect = ImportError("no driver")
    with pytest.raises(SourceError):
        c.fetch()


def test_incremental_passes_since_param(monkeypatch):
    c, _, _ = make(monkeypatch, query="SELECT * FROM t WHERE updated_at >= :since")
    seen = {}
    def rec(q, conn, params=None): seen["q"], seen["p"] = str(q), params; return RAW
    monkeypatch.setattr(sqlmod.pd, "read_sql", rec)
    c.fetch(since="2026-01-01")
    assert seen["p"] == {"since": "2026-01-01"} and ":since" in seen["q"]


def test_full_refresh_fallback_when_no_since(monkeypatch):
    c, _, _ = make(monkeypatch, query="SELECT id,n,a,p FROM t WHERE updated_at >= :since",
                   full_query="SELECT id,n,a,p FROM t")
    seen = {}
    def rec(q, conn, params=None): seen["q"], seen["p"] = str(q), params; return RAW
    monkeypatch.setattr(sqlmod.pd, "read_sql", rec)
    c.fetch()
    assert ":since" not in seen["q"] and seen["p"] == {}


def test_char_padding_nulls_and_text_pin_from_db(monkeypatch):
    raw = pd.DataFrame({"id": [1, 2], "n": ["A   ", None], "a": ["x  ", "y"], "p": [600002, None]})
    c, _, _ = make(monkeypatch)
    monkeypatch.setattr(sqlmod.pd, "read_sql", lambda *a, **k: raw)
    df = c.fetch()
    assert df.source_id.tolist() == ["CRM:1", "CRM:2"]
    assert df.name.tolist() == ["A", ""] and df.pin.tolist() == ["600002", ""]


# ---------- MDM write-back with a mocked engine ----------

def mdm_setup(monkeypatch, count_override=None):
    g = pd.DataFrame([{"golden_id": "G1", "source": "sap", "cust_id": "1", "name": "A", "address": "x", "pin": "600002",
                       "method": "fuzzy", "score": 100.0, "reason": "r", "timestamp": "t"}])
    engine, conn, tx = MagicMock(), MagicMock(), MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.begin.return_value.__enter__.return_value = tx
    conn.execute.return_value.scalar.return_value = count_override if count_override is not None else 1
    monkeypatch.setattr("sqlalchemy.create_engine", MagicMock(return_value=engine))
    loaded = []
    monkeypatch.setattr(pd.DataFrame, "to_sql", lambda self, name, *a, **k: loaded.append(name))
    return g, engine, tx, loaded


def test_mdm_staging_load_verify_then_single_transaction_swap(monkeypatch):
    g, engine, tx, loaded = mdm_setup(monkeypatch)
    msg = mdm_writer.write_mdm(g, "fake://mdm")
    assert msg.startswith("written")
    assert any(n.endswith("_stg") for n in loaded)                 # staging tables loaded first
    engine.begin.assert_called_once()                              # exactly one swap transaction
    sql = " ".join(str(c.args[0]) for c in tx.execute.call_args_list)
    assert "DELETE FROM customer_golden" in sql and "INSERT INTO customer_golden SELECT * FROM customer_golden_stg" in sql
    engine.dispose.assert_called_once()


def test_mdm_count_mismatch_aborts_before_swap(monkeypatch):
    g, engine, tx, _ = mdm_setup(monkeypatch, count_override=999)
    with pytest.raises(RuntimeError):
        mdm_writer.write_mdm(g, "fake://mdm")
    engine.begin.assert_not_called()                               # live tables untouched
    engine.dispose.assert_called_once()


def test_mdm_never_touches_source_tables(monkeypatch):
    g, engine, tx, loaded = mdm_setup(monkeypatch)
    mdm_writer.write_mdm(g, "fake://mdm")
    sql = " ".join(str(c.args[0]) for c in tx.execute.call_args_list)
    assert not any(t in sql for t in ("KNA1", "accounts", "customers"))
    assert all(n.startswith(("customer_", "sap_customer_")) for n in loaded)
