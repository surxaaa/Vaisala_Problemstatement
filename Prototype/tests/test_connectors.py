import json, pandas as pd, pytest
from connectors import build_connectors, SourceError, STANDARD_COLS
from connectors.base import SourceConnector
from connectors.sql import SqlConnector
from src.staging import extract_all, to_pipeline_frame
from src.mdm_writer import build_mdm_frames, write_mdm

COLS = {"source_id": "id", "name": "n", "address": "a", "pin": "p"}

class Fake(SourceConnector):
    def __init__(self, system, raw, fail=False):
        super().__init__(system, {"columns": COLS}); self.raw, self.fail = raw, fail
    def _extract(self, since=None):
        if self.fail: raise TimeoutError("db down")
        return self.raw

def raw(**kw):
    d = {"id": ["1001"], "n": ["Acetech  "], "a": [None], "p": ["600 002"]}; d.update(kw)
    return pd.DataFrame(d)

def test_standard_shape_prefix_null_and_char_padding():
    df = Fake("sap", raw()).fetch()
    assert list(df.columns) == STANDARD_COLS
    assert df.source_id[0] == "SAP:1001" and df.name[0] == "Acetech" and df.address[0] == ""

def test_same_id_in_two_systems_does_not_clash():
    a, b = Fake("sap", raw()).fetch(), Fake("crm", raw()).fetch()
    assert a.source_id[0] != b.source_id[0]

def test_missing_source_column_raises():
    with pytest.raises(SourceError):
        Fake("sap", raw().drop(columns=["n"])).fetch()

def test_extract_error_wrapped_without_payload():
    with pytest.raises(SourceError) as e:
        Fake("sap", raw(), fail=True).fetch()
    assert "TimeoutError" in str(e.value) and "db down" not in str(e.value)

def test_required_source_down_fails_run(tmp_path):
    conns = {"sap": Fake("sap", raw()), "crm": Fake("crm", raw(), fail=True)}
    with pytest.raises(SourceError):
        extract_all(conns, ["sap", "crm"], str(tmp_path), run_id="r1")
    assert json.load(open(tmp_path / "r1" / "manifest.json"))["crm"]["error"]

def test_snapshot_and_manifest_written(tmp_path):
    frames, man, d = extract_all({"sap": Fake("sap", raw())}, ["sap"], str(tmp_path), run_id="r1")
    assert man["sap"]["rows"] == 1 and (tmp_path / "r1" / "sap.csv").exists()
    pf = to_pipeline_frame(frames)
    assert pf.cust_id[0] == "1001" and pf.source[0] == "sap" and pf.pin[0] == "600002"

def test_sql_connector_requires_env_var(monkeypatch):
    monkeypatch.delenv("X_URL", raising=False)
    c = SqlConnector("sap", {"columns": COLS, "url_env": "X_URL", "query": "SELECT 1"})
    with pytest.raises(SourceError):
        c.fetch()

def test_csv_config_builds():
    from connectors import load_config
    conns = build_connectors(load_config("config/connectors.yaml"))
    assert set(conns) == {"sap", "crm", "billing"}
    assert len(conns["sap"].fetch()) == 4

def test_mdm_write_skipped_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DB_URL", raising=False)
    assert write_mdm(pd.DataFrame()).startswith("skipped")

def test_mdm_frames_shape():
    g = pd.DataFrame([{"golden_id": "G1", "source": "sap", "cust_id": "1", "name": "A", "address": "x", "pin": "600002",
                       "method": "fuzzy", "score": 100.0, "reason": "r", "timestamp": "t"},
                      {"golden_id": "G1", "source": "crm", "cust_id": "9", "name": "A", "address": "x", "pin": "600002",
                       "method": "fuzzy", "score": 100.0, "reason": "r", "timestamp": "t"}])
    f = build_mdm_frames(g)
    assert set(f) == {"customer_golden", "customer_xref", "sap_customer_clean", "crm_customer_clean"}
    assert f["customer_golden"].member_count[0] == 2 and f["customer_xref"].source_id.tolist() == ["SAP:1", "CRM:9"]
