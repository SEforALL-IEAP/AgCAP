"""
irrigation_extraction_MOZ.py
----------------------------
Enriches an AgCAP settlement dataset with irrigation need indicators derived
from the TerraClimate climatological dataset via Google Earth Engine (GEE).

Run from the terminal:
    python irrigation_extraction_MOZ.py

See README_irrigation_extraction.md for full documentation.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog

import ee
import geemap
import pandas as pd
import geopandas as gpd


# =========================================================
# CONSTANTS
# =========================================================

COLUMN_RENAMES = {
    "rainfed_months":      "Irrigation: months with no need (rainfed)",
    "supplemental_months": "Irrigation: months with (moderate) need",
    "severe_months":       "Irrigation: months with (critical) need",
    "red_yellow_months":   "Irrigation: months with (moderate + critical) need",
}

OUTPUT_EXTENSIONS = {"fgb": ".fgb", "gpkg": ".gpkg", "csv": ".csv"}
OUTPUT_DRIVERS    = {"fgb": "FlatGeobuf", "gpkg": "GPKG"}

SEPARATOR = "  " + "─" * 62


# =========================================================
# TERMINAL UI HELPERS
# =========================================================

def banner():
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║         AgCAP  ·  Irrigation Needs Extraction Tool          ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()


def section(title):
    """Print a bold step/section header with surrounding blank lines."""
    print()
    print("  " + "═" * 62)
    print(f"  {title}")
    print("  " + "═" * 62)


def _prompt_block(label, explanation):
    """Print the label and explanation lines of a prompt block."""
    print()
    print("  ┌─ " + label + " " + "─" * max(0, 57 - len(label)) + "┐")
    for line in explanation.splitlines():
        print(f"  │  {line}")
    print("  └" + "─" * 62 + "┘")


def prompt_str(label, explanation, default=None):
    """Ask for a free-text value, showing an explanation and optional default."""
    _prompt_block(label, explanation)
    if default is not None:
        raw = input(f"  ▶  Your answer (press Enter to keep default: {default}): ").strip()
        return raw if raw else str(default)
    else:
        while True:
            raw = input("  ▶  Your answer (required): ").strip()
            if raw:
                return raw
            print("  ✖  This field is required — please enter a value.")


def prompt_int(label, explanation, default, min_val=None, max_val=None):
    """Ask for an integer value with validation."""
    _prompt_block(label, explanation)
    while True:
        raw = input(f"  ▶  Your answer (press Enter to keep default: {default}): ").strip()
        if not raw:
            return default
        try:
            val = int(raw)
            if min_val is not None and val < min_val:
                print(f"  ✖  Value must be ≥ {min_val}.")
                continue
            if max_val is not None and val > max_val:
                print(f"  ✖  Value must be ≤ {max_val}.")
                continue
            return val
        except ValueError:
            print("  ✖  Please enter a whole number.")


def prompt_float(label, explanation, default, min_val=None, max_val=None):
    """Ask for a float value with validation."""
    _prompt_block(label, explanation)
    while True:
        raw = input(f"  ▶  Your answer (press Enter to keep default: {default}): ").strip()
        if not raw:
            return default
        try:
            val = float(raw)
            if min_val is not None and val < min_val:
                print(f"  ✖  Value must be ≥ {min_val}.")
                continue
            if max_val is not None and val > max_val:
                print(f"  ✖  Value must be ≤ {max_val}.")
                continue
            return val
        except ValueError:
            print("  ✖  Please enter a number.")


def prompt_menu(label, explanation, options):
    """
    Display a numbered menu and return the chosen value.
    options: list of (value, description) tuples; first entry is the default.
    """
    _prompt_block(label, explanation)
    print()
    for i, (_, desc) in enumerate(options, start=1):
        marker = "  ◀ default" if i == 1 else ""
        print(f"  {i})  {desc}{marker}")
    print()
    while True:
        raw = input(f"  ▶  Your choice (press Enter to keep default: 1): ").strip()
        if not raw:
            return options[0][0]
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        except ValueError:
            pass
        print(f"  ✖  Please enter a number between 1 and {len(options)}.")


def open_tk_dialog(dialog_fn, message, **kwargs):
    """
    Run a tkinter dialog function, printing `message` first.
    Returns the result (path string or empty string).
    """
    print()
    print(f"  {message}")
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result = dialog_fn(**kwargs)
    root.destroy()
    return result


# =========================================================
# STEP 1 — INPUT FILE
# =========================================================

def ask_input_file():
    section("Step 1 of 6 — Input file")
    print()
    print("  Please select the AgCAP output file you want to enrich.")
    print("  Accepted formats: FlatGeobuf (.fgb) or CSV (.csv).")
    print("  A file browser window will open.")

    while True:
        path = open_tk_dialog(
            filedialog.askopenfilename,
            "Opening file browser — select your AgCAP input file…",
            title="Select AgCAP input file",
            filetypes=[
                ("Supported files", "*.fgb *.csv"),
                ("FlatGeobuf",      "*.fgb"),
                ("CSV",             "*.csv"),
                ("All files",       "*.*"),
            ],
        )
        if path:
            print(f"  ✔  Selected: {path}")
            return path
        print()
        print("  No file was selected.")
        retry = input("  Try again? [Y/n]: ").strip().lower()
        if retry in ("n", "no"):
            print("  Exiting.")
            sys.exit(0)


# =========================================================
# STEP 2 — OUTPUT FOLDER AND FILE NAME
# =========================================================

def ask_output_dir():
    section("Step 2a of 6 — Output folder")
    print()
    print("  Please select the folder where the output file will be saved.")
    print("  A folder browser window will open.")

    while True:
        path = open_tk_dialog(
            filedialog.askdirectory,
            "Opening folder browser — select the output folder…",
            title="Select output folder",
            mustexist=False,
        )
        if path:
            print(f"  ✔  Selected: {path}")
            return path
        print()
        print("  No folder was selected.")
        retry = input("  Try again? [Y/n]: ").strip().lower()
        if retry in ("n", "no"):
            print("  Exiting.")
            sys.exit(0)


def ask_output_filename(input_path):
    suggested = os.path.splitext(os.path.basename(input_path))[0] + "_irrigation"
    name = prompt_str(
        "Output file name (without extension)",
        f"The file extension will be added automatically depending on the format\n"
        f"you choose in the next question.\n"
        f"Suggested name (based on your input file): {suggested}",
        default=suggested,
    )
    return name


def ask_output_format():
    section("Step 2b of 6 — Output file format")
    return prompt_menu(
        "Output file format",
        "Choose the format for the enriched output file.\n"
        "FlatGeobuf and GeoPackage retain full geometry (points + attributes).\n"
        "CSV drops the geometry and saves attributes only.",
        [
            ("fgb",  "FlatGeobuf (.fgb)  — fast, compact spatial format, ideal for QGIS"),
            ("gpkg", "GeoPackage (.gpkg) — broadly compatible (QGIS, ArcGIS, GDAL)"),
            ("csv",  "CSV (.csv)         — tabular only, geometry column is dropped"),
        ],
    )


# =========================================================
# STEP 3 — GEE PROJECT
# =========================================================

def ask_gee_project():
    section("Step 3 of 6 — Google Earth Engine project")
    print()
    print("  This tool retrieves climate data from Google Earth Engine (GEE).")
    print("  You need a free GEE account and a linked Google Cloud project.")
    print()
    print("  ▸ Sign up at : https://earthengine.google.com/signup")
    print("  ▸ Find your project ID at: https://code.earthengine.google.com/")
    print("    (it appears in the top-left dropdown, e.g. 'ee-yourname')")

    while True:
        raw = input("\n  ▶  Your GEE project ID (required): ").strip()
        if raw:
            return raw
        print("  ✖  A project ID is required to continue.")


# =========================================================
# STEP 4 — STUDY PERIOD
# =========================================================

def ask_study_period():
    section("Step 4 of 6 — Study period")
    print()
    print("  The tool computes a long-term monthly climatology over the period")
    print("  you define. A longer period produces more stable averages.")
    print("  TerraClimate data is available from 1958 to the present.")

    while True:
        start = prompt_int(
            "Start year",
            "First year of the climatological period (inclusive). Min: 1958.",
            default=2004,
            min_val=1958,
            max_val=2100,
        )
        end = prompt_int(
            "End year",
            "Last year of the climatological period (inclusive). Must be ≥ start year.",
            default=2024,
            min_val=1958,
            max_val=2100,
        )
        if end >= start:
            return start, end
        print(f"  End year ({end}) must be greater than or equal to start year ({start}). Please re-enter.")


# =========================================================
# STEP 5 — ADVANCED PARAMETERS
# =========================================================

def ask_advanced_parameters():
    section("Step 5 of 6 — Advanced parameters")
    print()
    print("  The following parameters control the agronomic classification and")
    print("  the GEE extraction behaviour. The defaults work well in most cases.")
    print("  Press Enter to accept each default, or type a new value.")

    base_temp = prompt_float(
        "Base temperature (°C)",
        "Months where mean temperature falls below this threshold are classified\n"
        "as 'dormant' (growing season inactive) regardless of water availability.\n"
        "Recommended: 5 °C for most tropical and sub-tropical regions.",
        default=5.0,
        min_val=-20.0,
        max_val=30.0,
    )

    scale = prompt_int(
        "Extraction scale (metres)",
        "Spatial resolution used when sampling TerraClimate data in GEE.\n"
        "TerraClimate's native resolution is ~4,000 m (4 km).\n"
        "Using a lower value does NOT add detail but greatly increases\n"
        "computation time. Keep at 4000 unless you have a specific reason.",
        default=4000,
        min_val=100,
        max_val=50000,
    )

    chunk_size = prompt_int(
        "Chunk size (number of points per GEE request)",
        "The input points are sent to GEE in batches of this size.\n"
        "Larger chunks mean fewer round-trips but higher memory use.\n"
        "If you encounter payload or timeout errors, reduce this value\n"
        "(e.g. 250 or 500). Default of 1000 is suitable for most datasets.",
        default=1000,
        min_val=1,
        max_val=5000,
    )

    return base_temp, scale, chunk_size


# =========================================================
# STEP 6 — REVIEW AND CONFIRM
# =========================================================

def confirm_all(cfg):
    section("Step 6 of 6 — Review and confirm")
    print()
    print("  Please review the configuration below before processing begins.")
    print("  If anything is incorrect, type 'n' to abort and restart the script.")
    print()

    W = 44  # value column width
    rows = [
        ("Input file",        cfg["input_path"]),
        ("Output folder",     cfg["output_dir"]),
        ("Output file name",  cfg["output_name"] + OUTPUT_EXTENSIONS[cfg["output_format"]]),
        ("Output format",     cfg["output_format"].upper()),
        ("GEE project",       cfg["gee_project"]),
        ("Study period",      f"{cfg['start_year']} – {cfg['end_year']}"),
        ("Base temperature",  f"{cfg['base_temp']} °C  (dormant threshold)"),
        ("Extraction scale",  f"{cfg['scale']} m  (TerraClimate native: ~4,000 m)"),
        ("Chunk size",        f"{cfg['chunk_size']} points per GEE request"),
    ]

    print("  ┌──────────────────────┬" + "─" * (W + 2) + "┐")
    for label, value in rows:
        # Wrap long values
        value_str = str(value)
        if len(value_str) > W:
            value_str = "…" + value_str[-(W - 1):]
        print(f"  │ {label:<20} │ {value_str:<{W}} │")
    print("  └──────────────────────┴" + "─" * (W + 2) + "┘")
    print()

    while True:
        ans = input("  ▶  Proceed? (press Enter or type Y to start, N to abort): ").strip().lower()
        if ans in ("", "y", "yes"):
            return
        if ans in ("n", "no"):
            print()
            print("  Aborted. Restart the script to re-enter your settings.")
            sys.exit(0)


# =========================================================
# GEE AUTHENTICATION
# =========================================================

def initialize_gee(project_id):
    section("Connecting to Google Earth Engine")
    print()

    try:
        ee.Initialize(project=project_id)
        print(f"  ✔  Connected to GEE project: {project_id}")
        return
    except Exception:
        pass

    print("  Could not authenticate automatically. Starting authentication flow.")
    print()
    print("  What will happen next:")
    print("  1. A browser window will open — sign in with the Google account")
    print("     linked to your GEE account and grant the requested access.")
    print("  2. After approval, return to this terminal.")
    print("  3. Your credentials are saved locally; future runs authenticate")
    print("     automatically without repeating this step.")
    print()
    input("  Press Enter to open the browser…")

    ee.Authenticate()

    try:
        ee.Initialize(project=project_id)
        print()
        print(f"  ✔  Authentication successful. Connected to: {project_id}")
    except Exception as exc:
        print()
        print("  ✖  Initialisation failed after authentication.")
        print(f"     Error: {exc}")
        print()
        print("  Possible causes:")
        print("  • The project ID is misspelled or does not exist.")
        print("  • Your GEE account does not have access to this project.")
        print("  • You signed in with a different Google account than the one")
        print("    registered with GEE.")
        sys.exit(1)


# =========================================================
# GEE PROCESSING PIPELINE
# =========================================================

def build_extraction_image(start_year, end_year, base_temp):
    terraclimate = (
        ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE")
        .filterDate(f"{start_year}-01-01", f"{end_year + 1}-01-01")
    )

    def process_month(m):
        m = ee.Number(m)
        mean_img = terraclimate.filter(
            ee.Filter.calendarRange(m, m, "month")
        ).mean()

        pr_raw = mean_img.select("pr")
        coastal_mask = pr_raw.mask().focalMax(1, "square", "pixels")

        def scaled_band(name):
            raw = mean_img.select(name).multiply(0.1)
            return raw.unmask(raw.focalMean(1, "square", "pixels")).updateMask(coastal_mask)

        pet  = scaled_band("pet")
        aet  = scaled_band("aet")
        tmmx = scaled_band("tmmx")
        tmmn = scaled_band("tmmn")

        tmean       = tmmx.add(tmmn).divide(2)
        safe_pet    = pet.where(pet.eq(0), 0.001)
        stress_ratio = aet.divide(safe_pet)

        fao_class = (
            ee.Image(0)
            .where(stress_ratio.gte(0.5), 1)
            .where(stress_ratio.gte(0.8), 2)
            .where(tmean.lt(base_temp), 3)
            .updateMask(coastal_mask)
            .rename("fao_class")
        )
        return fao_class.set("month", m)

    months  = ee.List.sequence(1, 12)
    monthly = ee.ImageCollection.fromImages(months.map(process_month))

    severe_months  = monthly.map(lambda img: img.eq(0)).sum().rename("severe_months")
    supp_months    = monthly.map(lambda img: img.eq(1)).sum().rename("supplemental_months")
    rainfed_months = monthly.map(lambda img: img.eq(2)).sum().rename("rainfed_months")
    red_yellow     = severe_months.add(supp_months).rename("red_yellow_months")

    return ee.Image([rainfed_months, supp_months, severe_months, red_yellow]).toInt()


# =========================================================
# VECTOR LOADING
# =========================================================

def load_vector(path):
    ext = os.path.splitext(path)[1].lower()

    if ext == ".fgb":
        gdf = gpd.read_file(path, engine="pyogrio")
    elif ext == ".csv":
        df = pd.read_csv(path)
        if "geometry" in df.columns:
            import shapely.wkt
            df["geometry"] = df["geometry"].apply(shapely.wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
        elif {"lon", "lat"}.issubset(df.columns):
            gdf = gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326"
            )
        elif {"longitude", "latitude"}.issubset(df.columns):
            gdf = gpd.GeoDataFrame(
                df,
                geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
                crs="EPSG:4326",
            )
        else:
            print(
                "  ✖  CSV has no recognised geometry column.\n"
                "     Expected: 'geometry' (WKT), or 'lon'/'lat', or 'longitude'/'latitude'."
            )
            sys.exit(1)
    else:
        print(f"  ✖  Unsupported file format: {ext}")
        sys.exit(1)

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    return gdf


# =========================================================
# CHUNKED GEE EXTRACTION
# =========================================================

def extract_chunked(extraction_image, gdf, chunk_size, scale):
    gdf = gdf.copy()
    gdf["_tid"] = range(len(gdf))

    total   = len(gdf)
    n_chunks = (total + chunk_size - 1) // chunk_size
    print(f"  Total points : {total:,}")
    print(f"  Chunk size   : {chunk_size:,}  →  {n_chunks} request(s) to GEE")
    print()

    results = []
    for i in range(0, total, chunk_size):
        chunk_num = i // chunk_size + 1
        chunk     = gdf.iloc[i : i + chunk_size][["_tid", "geometry"]]
        end_idx   = min(i + chunk_size, total)
        print(f"  [{chunk_num:>3}/{n_chunks}] Points {i + 1:,}–{end_idx:,}…", end=" ", flush=True)

        ee_fc = geemap.geopandas_to_ee(chunk)
        extracted = extraction_image.reduceRegions(
            collection=ee_fc,
            reducer=ee.Reducer.mean(),
            scale=scale,
            tileScale=4,
        )

        try:
            features = extracted.getInfo()["features"]
            rows = [f["properties"] for f in features]
            results.append(pd.DataFrame(rows))
            print("✔")
        except Exception as exc:
            print(f"✖  Error: {exc}")

    return results, gdf


# =========================================================
# OUTPUT SAVING
# =========================================================

def save_output(final_gdf, output_dir, output_name, output_format):
    os.makedirs(output_dir, exist_ok=True)
    ext      = OUTPUT_EXTENSIONS[output_format]
    out_path = os.path.join(output_dir, output_name + ext)

    if output_format == "csv":
        df = final_gdf.drop(columns=["geometry"], errors="ignore")
        df.to_csv(out_path, index=False)
    else:
        final_gdf.to_file(out_path, driver=OUTPUT_DRIVERS[output_format], engine="pyogrio")

    return out_path


# =========================================================
# MAIN
# =========================================================

def main():
    banner()

    print("  This tool enriches an AgCAP settlement point dataset with")
    print("  irrigation need indicators derived from TerraClimate climate")
    print("  data, accessed via Google Earth Engine.")
    print()
    print("  You will be guided through 6 steps to configure the run.")
    print("  Press Enter at any prompt to accept the suggested default.")

    # ── Steps 1–2: files ────────────────────────────────────────────────────
    input_path    = ask_input_file()
    output_dir    = ask_output_dir()
    output_name   = ask_output_filename(input_path)
    output_format = ask_output_format()

    # ── Step 3: GEE project ─────────────────────────────────────────────────
    gee_project = ask_gee_project()

    # ── Step 4: study period ────────────────────────────────────────────────
    start_year, end_year = ask_study_period()

    # ── Step 5: advanced parameters ─────────────────────────────────────────
    base_temp, scale, chunk_size = ask_advanced_parameters()

    # ── Step 6: confirm ─────────────────────────────────────────────────────
    cfg = dict(
        input_path    = input_path,
        output_dir    = output_dir,
        output_name   = output_name,
        output_format = output_format,
        gee_project   = gee_project,
        start_year    = start_year,
        end_year      = end_year,
        base_temp     = base_temp,
        scale         = scale,
        chunk_size    = chunk_size,
    )
    confirm_all(cfg)

    # ── GEE authentication ───────────────────────────────────────────────────
    initialize_gee(gee_project)

    # ── Build GEE pipeline ───────────────────────────────────────────────────
    section("Building Earth Engine processing pipeline")
    print()
    extraction_image = build_extraction_image(start_year, end_year, base_temp)
    print("  ✔  Pipeline ready.")

    # ── Load vector data ─────────────────────────────────────────────────────
    section("Loading input data")
    print()
    gdf = load_vector(input_path)
    print(f"  ✔  Loaded {len(gdf):,} features.")

    # ── Extract ──────────────────────────────────────────────────────────────
    section("Extracting values from Google Earth Engine")
    print()
    results, gdf = extract_chunked(extraction_image, gdf, chunk_size, scale)

    if not results:
        print()
        print("  ✖  No data was extracted. Please check the errors above.")
        sys.exit(1)

    # ── Merge ────────────────────────────────────────────────────────────────
    section("Merging results")
    print()
    extracted_stats = pd.concat(results, ignore_index=True).rename(columns=COLUMN_RENAMES)
    final_gdf = gdf.merge(extracted_stats, on="_tid", how="left").drop(columns=["_tid"])
    print(f"  ✔  Merged {len(final_gdf):,} records.")

    # ── Save ─────────────────────────────────────────────────────────────────
    section("Saving output")
    print()
    out_path = save_output(final_gdf, output_dir, output_name, output_format)
    print(f"  ✔  Saved to: {out_path}")
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║                    Extraction complete.                     ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
