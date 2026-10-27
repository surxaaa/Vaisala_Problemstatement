from connectors.sql import SqlConnector

class CrmConnector(SqlConnector):
    """Postgres: postgresql+psycopg2://...   SQL Server: mssql+pyodbc://...
    (Salesforce would need an API connector subclass implementing _extract.)"""
