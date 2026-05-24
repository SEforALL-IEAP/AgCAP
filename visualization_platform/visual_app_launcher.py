
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

project_root = Path(__file__).parent.parent

# 3. Insert the project root path into the system path
sys.path.insert(0, str(project_root))

from scripts.app import *

# --- NEW: Interactive File Selection ---

print("\n Opening file dialog... Please select the GeoPackage (.gpkg) dataset with the analyzed settlement points.")

# 1. Initialize a hidden Tkinter root window
root = tk.Tk()
root.withdraw() # Hide the main window (we only want the popup)
root.attributes('-topmost', True) # Attempt to force the window to the front

# 2. Open the File Explorer Dialog
# We set initialdir to a likely location to save the user time, but they can browse anywhere.
file_path_string = filedialog.askopenfilename(
    title="Select the Analysis Results Dataset",
    initialdir=project_root / 'data/processed', 
    filetypes=[("GeoPackage Files", "*.gpkg"), ("All Files", "*.*")]
)

# 3. Handle the case where the user clicks "Cancel"
if not file_path_string:
    print("\n ❌ No file selected. Exiting application.")
    sys.exit() # Stop the script

# 4. Convert string to Path object and proceed
settles_gdf_analyzed_path = Path(file_path_string)
print(f'\n ✅ Target dataset selected: {settles_gdf_analyzed_path}\n')

# --- End of Interactive Selection ---

settles_gdf_analyzed = gpd.read_file(settles_gdf_analyzed_path)

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
    figure_title="AgCAP results"
)

# Schedule the browser to open a few seconds AFTER the app starts
Timer(0.5, open_browser).start()

# Run the app
# Note: jupyter_mode='tab' is ignored when running as a standalone script, 
# but we leave it here for compatibility.
print("\n 🚀 Starting Server...")
print('\n Press CTRL+C to quit\n')
viz_results.run(port=8057)