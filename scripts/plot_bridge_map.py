"""Plot bridges from the GAD master data on a Gujarat district map.

The coordinate columns in the workbook are inconsistent: the LONGITUDE /
LATITUDE headers are swapped on many rows, some entries are DMS strings,
some lost their decimal point, and a few are UTM (zone 42N) metres. Each
row is parsed into a set of candidate (lat, lon) pairs and the first one
that falls inside the bridge's own district (else inside Gujarat) is kept.

Usage:  python3 scripts/plot_bridge_map.py
Writes: output/gujarat_bridge_map.png, output/bridges_geocoded.csv
"""

import re
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import Point

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "Master Data for GAD Module_09.07.2026.xlsx"
DISTRICTS = ROOT / "shapefiles-master/state_ut/gujarat/district/gujarat_district_2011.json"
STATES = ROOT / "shapefiles-master/india/state_ut/india_state.json"
OUT = ROOT / "output"

# Sheet -> column index of (district, taluka, first coordinate, second coordinate, name, length, span config)
SHEETS = {
    "Major Bridge": dict(district=6, taluka=7, c1=17, c2=18, name=22, length=21, config=28, condition=41),
    "Minor Bridge": dict(district=4, taluka=5, c1=15, c2=16, name=20, length=19, config=26, condition=39),
}
FIRST_DATA_ROW = 4

# Workbook district spellings -> 2011-census district(s) in the shapefile.
# Districts created in 2013 (and Vav-Tharad in 2025) map to their parents.
DISTRICT_ALIASES = {
    "ahmedabad": ["Ahmadabad"], "a'bad": ["Ahmadabad"], "ahemdabad": ["Ahmadabad"],
    "amreli": ["Amreli"], "anand": ["Anand"],
    "aravalli": ["Sabar Kantha"], "arvalli": ["Sabar Kantha"],
    "banas kantha": ["Banas Kantha"], "banaskantha": ["Banas Kantha"], "b.k.": ["Banas Kantha"],
    "b.k": ["Banas Kantha"], "vav tharad": ["Banas Kantha"], "vav-tharad": ["Banas Kantha"],
    "deodar": ["Banas Kantha"],
    "bharuch": ["Bharuch"], "bhavnagar": ["Bhavnagar"], "botad": ["Ahmadabad", "Bhavnagar"],
    "chhota udepur": ["Vadodara"], "chhotaudepur": ["Vadodara"], "chhotaudaipur": ["Vadodara"],
    "dahod": ["Dohad"], "dang": ["The Dangs"],
    "devbhumi dwarka": ["Jamnagar"], "devbhumidwarka": ["Jamnagar"], "devbhoomi dwarka": ["Jamnagar"],
    "gandhinagar": ["Gandhinagar"],
    "gir somnath": ["Junagadh"], "gir-somnath": ["Junagadh"], "girsomnath": ["Junagadh"],
    "jamnagar": ["Jamnagar"], "junagadh": ["Junagadh"],
    "kachchh": ["Kachchh"], "kutch": ["Kachchh"], "kheda": ["Kheda"],
    "mahisagar": ["Kheda", "Panch Mahals"],
    "mehsana": ["Mahesana"], "mahesana": ["Mahesana"], "mehasana": ["Mahesana"],
    "morbi": ["Rajkot", "Surendranagar", "Jamnagar"],
    "narmada": ["Narmada"], "navsari": ["Navsari"],
    "panchmahal": ["Panch Mahals"], "punchmahal": ["Panch Mahals"],
    "patan": ["Patan"], "porbandar": ["Porbandar"], "rajkot": ["Rajkot"],
    "sabarkantha": ["Sabar Kantha"], "himmatnagar": ["Sabar Kantha"],
    "surat": ["Surat"], "surendranagar": ["Surendranagar"],
    "tapi": ["Tapi"], "tapi-vyara": ["Tapi"],
    "vadodara": ["Vadodara"], "valsad": ["Valsad"],
}

TOLERANCE_DEG = 0.05  # ~5 km, for bridges on district/coast boundaries

UTM_TO_WGS84 = {z: Transformer.from_crs(f"EPSG:326{z}", "EPSG:4326", always_xy=True) for z in (42, 43)}


def parse_number(raw):
    """Return a float from a cell (decimal, DMS string, or plain number), or None."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not nums:
        return None
    if len(nums) >= 2 and re.search(r"[°'\"’]", text):
        deg, minutes = nums[0], nums[1]
        sec = nums[2] if len(nums) > 2 else 0.0
        return deg + minutes / 60 + sec / 3600
    return nums[0]


def rescale_degrees(v):
    """Undo a missing decimal point, e.g. 22343699 -> 22.343699."""
    while v is not None and v > 90:
        v /= 10
    return v


def candidates(a, b):
    """Possible (lat, lon) readings of a raw coordinate pair, most likely first."""
    out = []
    if a is None or b is None:
        return out
    if a > 1e5 and b > 1e5:
        # UTM metres: northing is the larger value
        north, east = max(a, b), min(a, b)
        for z in (42, 43):
            lon, lat = UTM_TO_WGS84[z].transform(east, north)
            out.append((lat, lon))
    ra, rb = rescale_degrees(a), rescale_degrees(b)
    out += [(ra, rb), (rb, ra)]
    return [(lat, lon) for lat, lon in out if 19 < lat < 25.5 and 67.5 < lon < 75.5]


def load_bridges():
    frames = []
    xl = pd.ExcelFile(XLSX)
    for sheet, cols in SHEETS.items():
        raw = xl.parse(sheet, header=None).iloc[FIRST_DATA_ROW:]
        raw = raw[raw[cols["c1"]].notna() | raw[cols["c2"]].notna() | raw[cols["district"]].notna()]
        frames.append(pd.DataFrame({
            "sheet": sheet,
            "sr_no": raw[0].values,
            "district": raw[cols["district"]].fillna("").astype(str).str.strip().values,
            "taluka": raw[cols["taluka"]].values,
            "bridge_name": raw[cols["name"]].values,
            "length_m": raw[cols["length"]].values,
            "configuration": raw[cols["config"]].values,
            "condition": raw[cols["condition"]].values,
            "raw_coord_1": raw[cols["c1"]].values,
            "raw_coord_2": raw[cols["c2"]].values,
        }))
    return pd.concat(frames, ignore_index=True)


def load_districts():
    """Districts with polygon-only, valid geometry (the source file has self-intersections)."""
    districts = gpd.read_file(DISTRICTS)

    def polygons_only(g):
        parts = shapely.get_parts(shapely.make_valid(g))
        return shapely.union_all([p for p in parts if p.geom_type in ("Polygon", "MultiPolygon")])

    districts["geometry"] = districts.geometry.apply(polygons_only)
    return districts


def geocode(df, districts):
    # Simplify (~200 m) before buffering: buffering the full-resolution outline takes minutes
    simple = districts.geometry.simplify(0.002)
    state = simple.union_all().buffer(TOLERANCE_DEG)
    by_name = dict(zip(districts.district, simple.buffer(TOLERANCE_DEG)))
    shapely.prepare([state, *by_name.values()])  # makes the per-point contains() checks fast
    lats, lons, status = [], [], []
    for row in df.itertuples():
        cands = candidates(parse_number(row.raw_coord_1), parse_number(row.raw_coord_2))
        home = [by_name[d] for d in DISTRICT_ALIASES.get(row.district.lower(), [])]
        chosen, flag = None, "no usable coordinates"
        for lat, lon in cands:
            if any(g.contains(Point(lon, lat)) for g in home):
                chosen, flag = (lat, lon), "in district"
                break
        if chosen is None:
            for lat, lon in cands:
                if state.contains(Point(lon, lat)):
                    chosen, flag = (lat, lon), "in Gujarat, outside stated district"
                    break
        if chosen is None and cands:
            flag = "outside Gujarat"
        lats.append(chosen[0] if chosen else None)
        lons.append(chosen[1] if chosen else None)
        status.append(flag)
    df["latitude"], df["longitude"], df["geocode_status"] = lats, lons, status
    return df


def plot(df, districts):
    states = gpd.read_file(STATES)
    minx, miny, maxx, maxy = districts.total_bounds
    pad = 0.3

    fig, ax = plt.subplots(figsize=(13, 11), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#eef3f7")  # sea / outside India
    states.plot(ax=ax, color="#f1f0ec", edgecolor="#c9c7bf", linewidth=0.6)
    districts.plot(ax=ax, color="#ffffff", edgecolor="#8f8d86", linewidth=0.6)
    districts.dissolve().boundary.plot(ax=ax, color="#3d3c39", linewidth=1.2)

    located = df.dropna(subset=["latitude"])
    minor = located[located.sheet == "Minor Bridge"]
    major = located[located.sheet == "Major Bridge"]
    ax.scatter(minor.longitude, minor.latitude, s=4, color="#2a78d6", alpha=0.55, linewidths=0,
               label=f"Minor bridge ({len(minor):,})", zorder=3)
    ax.scatter(major.longitude, major.latitude, s=16, color="#eb6834", edgecolors="#ffffff",
               linewidths=0.4, label=f"Major bridge ({len(major):,})", zorder=4)

    for r in districts.itertuples():
        c = r.geometry.representative_point()
        ax.annotate(r.district, (c.x, c.y), ha="center", va="center", fontsize=7,
                    color="#52514e", zorder=5,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground="#ffffff")])

    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad, maxy + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude (°E)", color="#52514e")
    ax.set_ylabel("Latitude (°N)", color="#52514e")
    ax.tick_params(colors="#52514e", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#c9c7bf")

    total = len(df)
    ax.set_title("Bridges in Gujarat: GAD master data (09.07.2026)", fontsize=15, loc="left",
                 color="#0b0b0b", pad=24)
    ax.text(0, 1.012, f"{len(located):,} of {total:,} records plotted. The rest have missing or "
            "unusable coordinates. District boundaries are from the 2011 Census.",
            transform=ax.transAxes, fontsize=9, color="#52514e")
    leg = ax.legend(loc="lower left", frameon=True, fontsize=9, markerscale=2.5)
    leg.get_frame().set_edgecolor("#c9c7bf")

    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / "gujarat_bridge_map.png", bbox_inches="tight", facecolor=fig.get_facecolor())


def main():
    districts = load_districts()
    df = geocode(load_bridges(), districts)
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / "bridges_geocoded.csv", index=False)
    print(df.groupby(["sheet", "geocode_status"]).size().to_string())
    plot(df, districts)


if __name__ == "__main__":
    main()
