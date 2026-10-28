"""Group bridges into structural typologies that can share one OpenSees model.

A typology is the combination of what drives a bridge's structural model:

  superstructure type | number of spans (bin) | governing span length (bin)

Design era (from construction year) and substructure material are kept as
secondary attributes of each bridge: within one typology they change
member sizes / material properties, not the model topology.

All structural fields are parsed from the free-text "Bridge Configuration"
and "Sub Type" columns. Where the superstructure type is not stated and the
longest span is <= 12 m, the bridge is assumed to be an RCC solid slab (the
usual choice for short spans in Gujarat R&B practice). These rows are
flagged with superstructure_source = "assumed".

Usage:  python3 scripts/classify_bridge_typology.py   (after plot_bridge_map.py)
Writes: output/bridge_typology.csv           one row per bridge with its typology
        output/bridge_typology_summary.csv   one row per typology
        output/bridge_typology.xlsx          both of the above as sheets
        output/bridge_typology.md            readable list of the typologies
"""

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "output/bridges_geocoded.csv"
OUT = ROOT / "output"

# Superstructure keywords, checked in this order (first match wins)
SUPERSTRUCTURE_PATTERNS = [
    ("Causeway", r"causeway|cause way|c\.way"),
    ("Pipe culvert", r"\bpipe|hume|\bh\.?\s?p\.?\b|\bnp\s?[234]\b"),
    ("Box girder (RCC/PSC)", r"box\s*girder"),
    ("RCC box / box cell", r"\bbox"),
    ("Arch", r"arch"),
    ("Steel / truss", r"steel|truss|bailey"),
    ("PSC girder", r"p\.?\s?s\.?\s?c|prestress|pre-stress|pre stress"),
    # "deck slab" in Indian practice is the slab spanning between girders
    ("RCC T-beam / girder", r"t[\s.-]*bea[mn]|tee\s*beam|girder|beam|balanced cantilever|deck\s*slab"),
    ("RCC voided slab", r"voided"),
    ("RCC solid slab", r"slab|slab\s*drain"),
]

SUBSTRUCTURE_PATTERNS = [
    ("Masonry", r"masonry|masonary|brick|stone|u\.?c\.?r|rubble|\bcrm\b"),
    ("RCC", r"rcc\s*(pier|sub|wall|column|abutment|trestle)|pier.*rcc|sub\s*-?\s*structure\s*[-:]?\s*rcc|column|circular pier"),
]

ERA_BINS = [(0, 1980, "Pre-1980"), (1980, 2002, "1980-2001"), (2002, 2015, "2002-2014"), (2015, 2100, "2015 onwards")]
SPAN_COUNT_BINS = [(1, 1, "1 span"), (2, 3, "2-3 spans"), (4, 6, "4-6 spans"), (7, 12, "7-12 spans"), (13, 999, "13+ spans")]
MIN_BRIDGES_TO_LIST = 20  # typologies smaller than this are left to the spreadsheet
SPAN_LENGTH_BINS = [(0, 6, "span <= 6 m"), (6, 10, "span 6-10 m"), (10, 15, "span 10-15 m"),
                    (15, 25, "span 15-25 m"), (25, 40, "span 25-40 m"), (40, 1e9, "span > 40 m")]

NUM = r"(\d+(?:\.\d+)?)"
METRE = r"\s*(?:m\b|mt|mtr|meter|metre|mts)\.?"
# Each pattern finds (count, span) groups; a bridge may list several, e.g. "LHS 3x24.20 | RHS 6x12".
# "4 Span X 11.20", "2 x 8.00", "3*2.5", "2 span of 2.80", "Span-5*24.40", "(1nos x 3 meter)"
COUNT_X_SPAN = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:nos\.?|no\.?)?\s*(?:spans?)?\s*(?:of|x|\*|×|@)\s*" + NUM)
# "8 span 7 mt c/c", "5 SPan 7.00 Mtr", "RCC Slab (2 Span 7 m)", "2 no 12.10 m c/c span", "2 Span 12.20 C/C"
COUNT_THEN_SPAN = re.compile(r"(?<![\d.])(\d{1,2})\s*[-–]?\s*(?:(?:nos?\.?|spans?)\s*)+(?:of|@|[,(/:-])?\s*"
                             + NUM + r"(?:" + METRE + r"|\s*c/c)")
# "10 Mt x 2 SPAN", "7.5 meter C/C 3 span"
SPAN_THEN_COUNT = re.compile(NUM + METRE + r"\s*(?:c/c)?\s*(?:x|\*|×)?\s*(\d{1,2})\s*(?:nos\.?\s*)?spans?\b")
SPAN_COUNT_ONLY = re.compile(r"(?<![\d.])(\d{1,2})\s*[-–]?\s*(?:nos\.?\s*)?spans?\b")
SPAN_LENGTH_ONLY = re.compile(r"span\s*(?:length)?\s*[-:=]?\s*" + NUM + METRE)


def to_float(v):
    m = re.search(NUM, str(v)) if pd.notna(v) else None
    return float(m.group(1)) if m else None


def parse_spans(text, total_length):
    """Return (number of spans, governing span m, how it was found) from configuration text.

    Spans written in the text are kept even when they disagree with the total
    length: the span is what the model needs, and the total length column is
    the less reliable of the two (it sometimes includes approaches or is a typo).
    """
    t = str(text).lower().replace(",", " ") if pd.notna(text) else ""
    groups = [(int(n), float(l)) for n, l in COUNT_X_SPAN.findall(t)]
    if not groups:
        groups = [(int(n), float(l)) for n, l in COUNT_THEN_SPAN.findall(t)]
    if not groups:
        groups = [(int(n), float(l)) for l, n in SPAN_THEN_COUNT.findall(t)]
    groups = [(n, l) for n, l in groups if 1 <= n <= 60 and 1 <= l <= 150]
    if groups:
        n, span = sum(n for n, _ in groups), max(l for _, l in groups)
        if total_length and not 0.4 <= n * span / total_length <= 2.5:
            return n, span, "span text (disagrees with total length)"
        return n, span, "span text"
    count = SPAN_COUNT_ONLY.search(t)
    if count and total_length:
        n = int(count.group(1))
        if 1 <= n <= 60:
            return n, round(total_length / n, 2), "span count in text; span = length / n"
    length = SPAN_LENGTH_ONLY.search(t)
    if length and total_length:
        span = float(length.group(1))
        if 1 <= span <= 150:
            return max(1, round(total_length / span)), span, "span length in text; n = length / span"
    return None, None, "not stated"


def match(text, patterns):
    t = str(text).lower() if pd.notna(text) else ""
    return next((label for label, p in patterns if re.search(p, t)), None)


def bin_label(value, bins):
    if value is None or pd.isna(value):
        return "unknown"
    return next((label for lo, hi, label in bins if lo <= value <= hi or lo < value < hi), "unknown")


def era(year_raw):
    years = [int(y) for y in re.findall(r"(?<!\d)(1[89]\d\d|20[0-2]\d)(?!\d)", str(year_raw))]
    return bin_label(years[0], [(lo, hi - 1, label) for lo, hi, label in ERA_BINS]) if years else "unknown"


def classify(df):
    df["total_length_m"] = df.length_m.map(to_float)
    parsed = [parse_spans(c, L) for c, L in zip(df.configuration, df.total_length_m)]
    df["n_spans"] = [p[0] for p in parsed]
    df["governing_span_m"] = [p[1] for p in parsed]
    df["span_source"] = [p[2] for p in parsed]

    text = df.configuration.fillna("").astype(str) + " " + df.sub_type.fillna("").astype(str)
    df["superstructure"] = text.map(lambda t: match(t, SUPERSTRUCTURE_PATTERNS))
    df["superstructure_source"] = df.superstructure.notna().map({True: "stated", False: "not stated"})
    short = df.superstructure.isna() & (df.governing_span_m <= 12)
    df.loc[short, "superstructure"] = "RCC solid slab"
    df.loc[short, "superstructure_source"] = "assumed (span <= 12 m)"
    df["superstructure"] = df.superstructure.fillna("Unknown")

    df["substructure"] = df.configuration.map(lambda t: match(t, SUBSTRUCTURE_PATTERNS)).fillna("not stated")
    df["design_era"] = df.construction_year.map(era)
    df["span_count_class"] = df.n_spans.map(lambda v: bin_label(v, SPAN_COUNT_BINS))
    df["span_length_class"] = df.governing_span_m.map(lambda v: bin_label(v, SPAN_LENGTH_BINS))
    df["typology"] = df.superstructure + " | " + df.span_count_class + " | " + df.span_length_class
    return df


def summarise(df):
    g = df.groupby("typology")
    summary = pd.DataFrame({
        "superstructure": g.superstructure.first(),
        "span_count_class": g.span_count_class.first(),
        "span_length_class": g.span_length_class.first(),
        "bridges": g.size(),
        "major": g.sheet.apply(lambda s: (s == "Major Bridge").sum()),
        "minor": g.sheet.apply(lambda s: (s == "Minor Bridge").sum()),
        "superstructure_assumed": g.superstructure_source.apply(lambda s: s.str.startswith("assumed").sum()),
        "median_spans": g.n_spans.median(),
        "median_span_m": g.governing_span_m.median(),
        "span_range_m": g.governing_span_m.apply(lambda s: f"{s.min():g}-{s.max():g}" if s.notna().any() else ""),
        "median_length_m": g.total_length_m.median(),
        "substructure_masonry": g.substructure.apply(lambda s: (s == "Masonry").sum()),
        "substructure_rcc": g.substructure.apply(lambda s: (s == "RCC").sum()),
    })
    for _, _, label in ERA_BINS + [(0, 0, "unknown")]:
        summary[f"era {label}"] = g.design_era.apply(lambda s, label=label: (s == label).sum())
    summary = summary.sort_values("bridges", ascending=False).reset_index()
    summary.insert(0, "typology_id", [f"T{i + 1:02d}" for i in range(len(summary))])
    summary["cumulative_share_%"] = (100 * summary.bridges.cumsum() / summary.bridges.sum()).round(1)
    return summary


def write_markdown(summary, df, path):
    known = summary[~summary.typology.str.contains("unknown|Unknown")]
    defined = known[known.bridges >= MIN_BRIDGES_TO_LIST]
    lines = [
        "# Bridge typologies for OpenSees modelling",
        "",
        "Generated by `scripts/classify_bridge_typology.py` from the GAD master data (09.07.2026).",
        "Each typology is a group of bridges that can share one parametric OpenSees model:",
        "**superstructure type | number of spans | governing (longest) span**.",
        "",
        f"- {len(df):,} bridges were classified into {len(summary)} typologies.",
        f"- {known.bridges.sum():,} bridges ({100 * known.bridges.sum() / len(df):.0f}%) fall in "
        f"{len(known)} fully defined typologies.",
        f"- The {len(defined)} typologies below have at least {MIN_BRIDGES_TO_LIST} bridges each. "
        f"Together they cover {defined.bridges.sum():,} bridges ({100 * defined.bridges.sum() / len(df):.0f}%).",
        "- The full list, and the typology of every bridge, is in `bridge_typology.xlsx`.",
        "",
        "Columns: *assumed* = superstructure not written, taken as an RCC solid slab because the span is 12 m or less. "
        "*Masonry / RCC sub.* = substructure material where the text states it. "
        "The era columns count bridges by construction year: Pre-1980, 1980–2001, 2002–2014 "
        "(after the 2001 Bhuj earthquake) and 2015 onwards.",
        "",
        "| ID | Superstructure | Spans | Span | Bridges | Major / minor | Assumed | Median span (m) | Span range (m) "
        "| Median length (m) | Masonry / RCC sub. | Pre-1980 | 1980–2001 | 2002–2014 | 2015+ | Year unknown |",
        "|---|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in defined.itertuples():
        lines.append(
            f"| {r.typology_id} | {r.superstructure} | {r.span_count_class} | {r.span_length_class.replace('span ', '')} "
            f"| {r.bridges:,} | {r.major} / {r.minor} | {r.superstructure_assumed} | {r.median_span_m:g} | {r.span_range_m} "
            f"| {r.median_length_m:g} | {r.substructure_masonry} / {r.substructure_rcc} "
            f"| {r[summary.columns.get_loc('era Pre-1980') + 1]} | {r[summary.columns.get_loc('era 1980-2001') + 1]} "
            f"| {r[summary.columns.get_loc('era 2002-2014') + 1]} | {r[summary.columns.get_loc('era 2015 onwards') + 1]} "
            f"| {r[summary.columns.get_loc('era unknown') + 1]} |")
    gaps = summary[summary.typology.str.contains("unknown|Unknown")]
    lines += [
        "",
        "## Bridges that could not be placed in a defined typology",
        "",
        "These need the span arrangement or superstructure type from the GAD drawings or a site visit:",
        "",
        "| ID | Typology | Bridges |",
        "|---|---|--:|",
    ]
    lines += [f"| {r.typology_id} | {r.typology.replace(' | ', ' · ')} | {r.bridges:,} |" for r in gaps[gaps.bridges >= MIN_BRIDGES_TO_LIST].itertuples()]
    rest = gaps[gaps.bridges < MIN_BRIDGES_TO_LIST]
    lines.append(f"| | {len(rest)} smaller groups | {rest.bridges.sum():,} |")
    path.write_text("\n".join(lines) + "\n")


def main():
    df = classify(pd.read_csv(CSV))
    summary = summarise(df)
    df = df.merge(summary[["typology", "typology_id"]], on="typology")

    bridge_cols = ["typology_id", "typology", "sheet", "sr_no", "district", "taluka", "bridge_name", "sub_type",
                   "latitude", "longitude", "total_length_m", "n_spans", "governing_span_m", "span_source",
                   "superstructure", "superstructure_source", "substructure", "design_era", "construction_year",
                   "carriageway_m", "condition", "configuration"]
    bridges = df[bridge_cols].sort_values(["typology_id", "sheet", "sr_no"])
    bridges.to_csv(OUT / "bridge_typology.csv", index=False)
    summary.to_csv(OUT / "bridge_typology_summary.csv", index=False)
    with pd.ExcelWriter(OUT / "bridge_typology.xlsx") as xl:
        summary.to_excel(xl, sheet_name="Typology summary", index=False)
        bridges.to_excel(xl, sheet_name="Bridges", index=False)

    write_markdown(summary, df, OUT / "bridge_typology.md")

    known = summary[~summary.typology.str.contains("unknown|Unknown")]
    print(f"{len(df):,} bridges, {len(summary)} typologies; "
          f"{known.bridges.sum():,} bridges in {len(known)} fully defined typologies")
    print(df.span_source.value_counts().to_string())
    print(df.superstructure_source.value_counts().to_string())
    print(summary.head(30)[["typology_id", "typology", "bridges", "cumulative_share_%"]].to_string(index=False))


if __name__ == "__main__":
    main()
