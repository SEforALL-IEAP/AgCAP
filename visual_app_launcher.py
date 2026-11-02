
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

# Disable the loggers (too many logs)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Language shown first (it can also be switched inside the platform)
lang = select_language()

# Run the platform with all its languages side by side; it opens in the web browser
print("\n 🚀 Starting Server...")
run_platform(settles_gdf_analyzed, port=8057, lang=lang,
             default_column='Fish Cooling Potential ALL Markets', figure_title="AgCAP results")
