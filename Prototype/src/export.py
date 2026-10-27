import pandas as pd

DANGEROUS = ("=", "+", "-", "@", "\t", "\r")

def neutralize(v):
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(DANGEROUS) else s

def safe_export(df: pd.DataFrame, path: str):
    out = df.copy()
    for c in out.select_dtypes(include="object").columns:
        out[c] = out[c].map(neutralize)
    out.to_excel(path, index=False)
