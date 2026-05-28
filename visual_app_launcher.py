
import sys
import os
from pathlib import Path
import geopandas as gpd
import webbrowser
from threading import Timer
import logging

# Imports for the file dialog
import tkinter as tk
from tkinter import filedialog

project_root = Path(__file__).parent

# 3. Insert the project root path into the system path
sys.path.insert(0, str(project_root))

from scripts.app import *

# --- NEW: Interactive File Selection ---

print("\n Opening file dialog... Please select the analyzed settlement dataset.")
print(" Accepted formats: GeoPackage (.gpkg), FlatGeobuf (.fgb), GeoJSON (.geojson), CSV (.csv), Shapefile (.shp), Parquet (.parquet)")

# 1. Initialize a hidden Tkinter root window
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)

# 2. Open the File Explorer Dialog
file_path_string = filedialog.askopenfilename(
    title="Select the Analysis Results Dataset",
    initialdir=project_root / 'data/processed',
    filetypes=[
        ("Supported formats", "*.gpkg *.fgb *.geojson *.json *.csv *.shp *.parquet"),
        ("GeoPackage",        "*.gpkg"),
        ("FlatGeobuf",        "*.fgb"),
        ("GeoJSON",           "*.geojson *.json"),
        ("CSV",               "*.csv"),
        ("Shapefile",         "*.shp"),
        ("GeoParquet",        "*.parquet"),
        ("All files",         "*.*"),
    ],
)

# 3. Handle the case where the user clicks "Cancel"
if not file_path_string:
    print("\n No file selected. Exiting application.")
    sys.exit() # Stop the script

# 4. Convert string to Path object and proceed
settles_gdf_analyzed_path = Path(file_path_string)
print(f'\n ✅ Target dataset selected: {settles_gdf_analyzed_path}\n')

# --- End of Interactive Selection ---

settles_gdf_analyzed = gpd.read_file(settles_gdf_analyzed_path)

# --- Language selection ---

def select_language():
    options = [('en', 'English'), ('pt', 'Português')]
    print("\n Select language / Selecione o idioma:")
    for i, (_, name) in enumerate(options, 1):
        print(f"   {i}) {name}")
    while True:
        raw = input("\n Your choice (press Enter for English): ").strip()
        if not raw:
            return 'en'
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        except ValueError:
            pass
        print(" Please enter 1 or 2.")

lang = select_language()
print(f'\n Language selected: {lang}\n')

# Function to open the browser
def open_browser():
    # Use 127.0.0.1 or localhost
    webbrowser.open_new("http://127.0.0.1:8057")

# Disable the loggers (too many logs)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Initialize the app
viz_results = agcap_explorer(
    settles_gdf_analyzed,
    default_column='Fish Cooling Demand ALL Markets',
    figure_title="AgCAP results",
    lang=lang,
)

# Schedule the browser to open a few seconds AFTER the app starts
Timer(0.5, open_browser).start()

# Run the app
# Note: jupyter_mode='tab' is ignored when running as a standalone script, 
# but we leave it here for compatibility.
print("\n 🚀 Starting Server...")
print('\n Press CTRL+C to quit\n')
viz_results.run(port=8057)