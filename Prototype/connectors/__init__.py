import yaml
from connectors.base import SourceConnector, SourceError, STANDARD_COLS
from connectors.csv_source import CsvConnector
from connectors.sap import SapConnector
from connectors.crm import CrmConnector
from connectors.billing import BillingConnector

SQL_CLASSES = {"sap": SapConnector, "crm": CrmConnector, "billing": BillingConnector}


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_connectors(cfg: dict) -> dict:
    out = {}
    for name, scfg in cfg["sources"].items():
        cls = CsvConnector if scfg["type"] == "csv" else SQL_CLASSES[name]
        out[name] = cls(name, scfg)
    return out
