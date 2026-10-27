from connectors.sql import SqlConnector

class SapConnector(SqlConnector):
    """SAP HANA / S4. URL example: hana+hdbcli://USER:PASS@host:30015  (pip install hdbcli sqlalchemy-hana)
    Alternative: expose a CDS view / OData export and use a csv/odata connector."""
