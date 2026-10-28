"""Check how much of what an OpenSees bridge model needs is in the GAD master data.

Reads output/bridges_geocoded.csv (made by plot_bridge_map.py) and reports,
per sheet, the share of records that have each piece of structural data.
Free-text "Bridge Configuration" is searched with keyword patterns, so the
percentages for those rows are upper bounds: a keyword hit means the topic
is mentioned, not that a usable value is given.

Usage:  python3 scripts/assess_opensees_readiness.py
Writes: output/opensees_data_completeness.csv
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "output/bridges_geocoded.csv"
OUT = ROOT / "output/opensees_data_completeness.csv"

# Keyword patterns searched in the free-text configuration column
CONFIG_PATTERNS = {
    "Span count / span length": r"span|\d+\s*[x\*×]\s*\d",
    "Superstructure type": r"super|slab|girder|t-beam|t beam|box|arch|psc|rcc|steel|truss",
    "Substructure type": r"sub|pier|abutment|wall|column",
    "Foundation type": r"found|open|well|pile|raft",
    "Bearing type": r"bearing|elastomer|neoprene",
    "Pier height / HFL": r"height|\bht\b|hfl",
    "Material grade (M25, Fe500...)": r"\bm\s?\d{2}\b|fe\s?\d{3}|grade",
    "Skew angle": r"skew",
    "Section dimensions": r"depth|thick|\bmm\b",
}


def main():
    df = pd.read_csv(CSV)
    cfg = df.configuration.fillna("").astype(str).str.lower()
    checks = {
        "Located on map": df.latitude.notna(),
        "Total length": pd.to_numeric(df.length_m, errors="coerce") > 0,
        "Configuration text present": cfg.str.strip().str.len() > 2,
    }
    for label, pattern in CONFIG_PATTERNS.items():
        checks[label] = cfg.str.contains(pattern, regex=True)

    table = pd.DataFrame({
        sheet: {label: round(100 * mask[df.sheet == sheet].mean(), 1) for label, mask in checks.items()}
        for sheet in df.sheet.unique()
    })
    table["All bridges"] = {label: round(100 * mask.mean(), 1) for label, mask in checks.items()}
    table.index.name = "Data item (% of records)"
    table.to_csv(OUT)
    print(table.to_string())


if __name__ == "__main__":
    main()
