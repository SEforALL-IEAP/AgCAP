# AgCAP — Irrigation Needs Extraction Tool

`irrigation_extraction_MOZ.py` enriches an **AgCAP settlement dataset** with
irrigation need indicators derived from the
[TerraClimate](https://www.climatologylab.org/terraclimate.html) global
climatological dataset, accessed through **Google Earth Engine (GEE)**.

The script takes the point vector file produced by the AgCAP analysis and adds
four new attributes that describe, for each settlement, how many months per year
(on average over the selected study period) fall into each irrigation need
category:

| Output column | Meaning |
|---|---|
| `Irrigation: months with no need (rainfed)` | Months where rainfall alone is sufficient |
| `Irrigation: months with (moderate) need` | Months where supplemental irrigation is beneficial |
| `Irrigation: months with (critical) need` | Months where irrigation is essential for crop production |
| `Irrigation: months with (moderate + critical) need` | Combined moderate + critical months |

Values range from 0 to 12 (months per year).

---

## How it works

The script applies a monthly evapotranspiration stress model to TerraClimate
data. For each month and each pixel, it:

1. Computes the ratio of **Actual Evapotranspiration (AET)** to
   **Potential Evapotranspiration (PET)** — the *water stress ratio*.
2. Classifies each pixel into one of four categories:

   | Stress ratio | Temperature | Category |
   |---|---|---|
   | < 0.5 | any | Critical irrigation need |
   | 0.5 – 0.8 | any | Moderate (supplemental) irrigation need |
   | ≥ 0.8 | any | Rainfed (no irrigation needed) |
   | any | < base temp | Dormant (growing season inactive) |

3. Sums how many months per year each settlement falls into each category,
   averaging across the full study period.
4. Extracts those values at each settlement centroid via GEE's
   `reduceRegions` API and merges them back into the original dataset.

---

## Requirements

### Python version

Python **3.9 or later** is required.

### Required packages

The following packages must be installed in your Python environment:

| Package | Purpose |
|---|---|
| `earthengine-api` | Google Earth Engine Python client |
| `geemap` | GEE / GeoPandas interoperability |
| `geopandas` | Reading and writing spatial vector files |
| `pandas` | Tabular data handling |
| `pyogrio` | Fast vector I/O backend for GeoPandas |
| `tkinter` | File and folder browser dialogs (usually bundled with Python) |

Install all third-party packages with pip:

```bash
pip install earthengine-api geemap geopandas pandas pyogrio
```

Or with conda (recommended for the spatial stack):

```bash
conda install -c conda-forge geopandas pyogrio geemap
pip install earthengine-api
```

`tkinter` is included with standard Python on Windows and macOS. On Linux it
may need to be installed separately — see [Troubleshooting](#troubleshooting).

---

## Google Earth Engine account

GEE is a free cloud platform for geospatial analysis. A personal account and
a linked Google Cloud project are required to use this tool.

### 1 — Create a GEE account

1. Go to **<https://earthengine.google.com/signup>**
2. Sign in with a Google account and request access.
3. Approval is usually instant for non-commercial use.

### 2 — Find or create your Cloud project ID

1. Visit **<https://code.earthengine.google.com/>**
2. Your project ID is shown in the top-left dropdown (e.g. `ee-yourname`).
3. To create a new project, select **"New Project"** from that dropdown.
4. Note the project ID — you will be asked to enter it when the script runs.

### 3 — First-time authentication

The first time you run the script on a given machine, it will guide you through
a browser-based authentication flow. Your credentials are then saved locally,
so subsequent runs connect automatically.

---

## Running the script

The script is fully interactive — it guides you through all configuration steps
with explanations at each prompt. No command-line flags are required.

Make sure the Python environment with the required packages is active before
launching.

### Windows

Open **Command Prompt** or **PowerShell** and activate your environment:

```bat
:: With conda:
conda activate your-environment-name

:: With venv:
C:\path\to\your-venv\Scripts\activate
```

Then run the script from anywhere:

```bat
python C:\path\to\irrigation_extraction_MOZ.py
```


### macOS

Open **Terminal** and activate your environment:

```bash
# With conda:
conda activate your-environment-name

# With venv:
source /path/to/your-venv/bin/activate
```

Then run:

```bash
python /path/to/irrigation_extraction_MOZ.py
```

> **Note:** If a dialog window appears behind other windows, click the Python
> icon in the Dock to bring it to the front.

### Linux

Open a terminal and activate your environment:

```bash
# With conda:
conda activate your-environment-name

# With venv:
source /path/to/your-venv/bin/activate
```

Then run:

```bash
python /path/to/irrigation_extraction_MOZ.py
```

---

## Interactive configuration walkthrough

When launched, the script guides you through **6 steps**. At each numeric
prompt, press **Enter** to accept the suggested default.

### Step 1 — Input file

A file browser window opens for you to select the AgCAP output file you want
to enrich. Accepted formats:

| Format | Notes |
|---|---|
| **FlatGeobuf** (`.fgb`) | Recommended — fast and compact |
| **CSV** (`.csv`) | Must contain a `geometry` column (WKT), or `lon`/`lat` (or `longitude`/`latitude`) columns |

### Step 2 — Output folder and file name

- A folder browser opens for you to choose where the output file will be saved.
- You are then asked for the output file name (without extension). A suggestion
  based on your input file name is offered.
- Finally you choose the output format:

| Format | Extension | Geometry retained | Best for |
|---|---|---|---|
| **FlatGeobuf** | `.fgb` | Yes | Fast loading in QGIS, further GIS processing |
| **GeoPackage** | `.gpkg` | Yes | Broad compatibility (QGIS, ArcGIS, GDAL) |
| **CSV** | `.csv` | No | Spreadsheet analysis, joining in other tools |

### Step 3 — Google Earth Engine project

You are asked to type your GEE Cloud project ID (e.g. `ee-yourname`). See
[Google Earth Engine account](#google-earth-engine-account) above for how to
find it.

### Step 4 — Study period

| Parameter | Default | Description |
|---|---|---|
| Start year | 2004 | First year of the climatological period (TerraClimate available from 1958) |
| End year | 2024 | Last year of the climatological period |

A longer period produces more stable averages. At least 10 years is recommended.

### Step 5 — Advanced parameters

| Parameter | Default | Description |
|---|---|---|
| Base temperature (°C) | 5 | Months where mean temperature falls below this value are classified as *dormant* (growing season inactive). Recommended: 5 °C for tropical and sub-tropical regions. |
| Extraction scale (m) | 4000 | Spatial resolution for GEE sampling. TerraClimate's native resolution is ~4,000 m. Lowering this does not add detail but greatly increases computation time. |
| Chunk size (points) | 1000 | Number of points sent to GEE per request. Reduce to 250–500 if you encounter timeout or payload errors. |

### Step 6 — Review and confirm

A summary table of all settings is printed. Type **Y** (or press Enter) to
start processing, or **n** to abort and restart.

---

## Troubleshooting

**`ee.EEException: Please authorize access`**  
→ The script will guide you through the browser authentication. Make sure you
sign in with the Google account registered with GEE.

**Wrong GEE project — initialisation fails after authentication**  
→ Re-run the script and double-check the project ID at Step 3. It must match
exactly what appears in the top-left dropdown at
[code.earthengine.google.com](https://code.earthengine.google.com/).

**`No module named 'ee'` or `No module named 'geemap'`**  
→ The required packages are not installed in the active environment. Run:
`pip install earthengine-api geemap`

**Extraction errors on some chunks**  
→ The script prints a warning and continues processing. Try reducing the chunk
size at Step 5 (e.g. 250) or increasing the scale to reduce payload size.

**Some settlements have `NaN` values in the output**  
→ Those points fall outside TerraClimate's coverage (e.g. small islands,
coastal margins). The coastal gap-filling logic handles most cases; residual
NaNs indicate pixels with no data in the source dataset.
