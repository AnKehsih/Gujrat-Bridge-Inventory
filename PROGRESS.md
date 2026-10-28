# Progress log

What was done in this repository, and why. Newest entries go at the top.

---

## 2026-10-28: Bridge location map and OpenSees data check

### 1. Read the master data workbook
**What:** Opened `Master Data for GAD Module_09.07.2026.xlsx`. It has two sheets:

| Sheet | Records | Coordinate columns |
|---|---|---|
| Major Bridge | 1,473 | R/S (index 17/18) |
| Minor Bridge | 8,982 | P/Q (index 15/16) |

The header takes up rows 1–4 (title, column names, LONGITUDE/LATITUDE sub-header, column numbers). Data starts at row 5.

**Why:** To find where the coordinates are and how clean they are before plotting.

### 2. Cleaned the coordinates (`scripts/plot_bridge_map.py`)
**What we found:** The coordinate entries are inconsistent:

- **Swapped columns.** About 4,900 rows have latitude (≈20–24.7°N) under the "LONGITUDE" header, and about 3,300 have it the right way round.
- **DMS strings**, written in many ways: `22°35'38"N`, `23'36'08"N`, `23° 46' 5.8368'' N`.
- **Decimals with suffixes or junk**, such as `72.199427 E` or ` 72.3805697)`.
- **Missing decimal point**, for example `22343699` for 22.343699 (Chhota Udepur rows).
- **UTM metres (zone 42N)**, for example `2319509.038, 741323.558` (Amreli and Gir Somnath rows) and `644988.44, 2495598.037` (Jamnagar/Dhrol rows).

**What we did:** For each row, the script builds every plausible (lat, lon) reading: both column orders, the decimal-point fix, and UTM zones 42/43. It keeps the first reading that falls inside the bridge's own district, with a ~5 km tolerance. If none does, it keeps the first reading that falls inside Gujarat. The workbook uses current district names, including the post-2013 districts and Vav-Tharad. The shapefile has the 26 districts from the 2011 Census, so each new district is mapped to its parent district(s).

**Why:** Taking the columns at face value would put most bridges in the wrong place. Checking each reading against the stated district catches mistakes that a simple range check misses. For example, `2319509 / 741323` is a valid UTM point on the Jafrabad coast, but it also reads as a valid but wrong point (23.19°N, 74.13°E) in Dahod.

**Result** (`output/bridges_geocoded.csv` has the status of every record):

| Status | Major | Minor |
|---|---|---|
| In stated district | 1,355 | 8,185 |
| In Gujarat, outside stated district | 60 | 576 |
| Outside Gujarat (not plotted) | 19 | 49 |
| No usable coordinates (not plotted) | 39 | 172 |

**Plotted: 10,176 of 10,455 records.** The "outside stated district" rows are plotted, but they should be checked by hand. Many are bridges on district boundaries, or districts that were split after 2011. The "outside Gujarat" rows are mostly Porbandar bridges whose longitude is given as ~68.0–68.4°E (out at sea). These are probably typos.

**Shapefile fix:** `gujarat_district_2011.json` has self-intersecting polygons, so union operations fail. The script repairs them with `make_valid` and keeps only the polygon parts. It also simplifies the outline (~200 m) before buffering. Without that, buffering the full-resolution outline takes about 2.5 minutes instead of under a second.

### 3. Drew the map (`output/gujarat_bridge_map.png`)
**What:** Gujarat's 2011 district boundaries, with neighbouring states in grey for context. Minor bridges are small blue dots and major bridges are larger orange dots.

**Why:** This is the map that was asked for: every bridge shown at its location from the lat/long data.

### 4. Checked whether the data is enough for OpenSees (`scripts/assess_opensees_readiness.py`)
**What:** Measured what share of records have each item an OpenSees model needs. The free-text "Bridge Configuration" column was searched with keywords, so those percentages are upper bounds. Output: `output/opensees_data_completeness.csv`.

| Data item | % of all records |
|---|---|
| Location (lat/long) | 97.3 |
| Total length | 96.1 |
| Span count / span length | 78.3 |
| Superstructure type (slab, box, girder…) | 52.9 |
| Substructure type | 11.6 |
| Foundation type | 3.4 |
| Bearing type | 0.0 |
| Pier height / HFL | 0.0 |
| Material grade | 0.0 |
| Skew angle | 0.0 |
| Section dimensions | 0.0 |

**Conclusion:** The data is **not enough** to build a bridge-specific OpenSees model. It lacks pier height, the dimensions of piers, deck and girders, reinforcement, concrete and steel grades, bearings, foundation and soil data, and skew. It is enough to **classify** bridges into typologies, for example by span count, span length, superstructure type, construction era and length. Those classes can then feed **parametric or archetype OpenSees models**, filled in with design-code values (IRC 6/21/112) or with typical GAD drawings for each class.

**Why:** This tells us whether the next step is modelling or collecting more data.

### Files added
- `scripts/plot_bridge_map.py`: coordinate cleaning, geocoding, map
- `scripts/assess_opensees_readiness.py`: data-completeness check
- `requirements.txt`: Python dependencies
- `output/gujarat_bridge_map.png`, `output/bridges_geocoded.csv`, `output/opensees_data_completeness.csv`
