import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context, clientside_callback, MATCH, ALL
import dash.dash_table.FormatTemplate as FormatTemplate
from dash.dash_table.Format import Format, Scheme
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go
import numpy as np
import base64
import io
import uuid
import json
import os
import tempfile
from datetime import datetime
import requests
import random
from shapely import wkt

# External stylesheet for Google Fonts (Mulish & Barlow Condensed) and Icons
external_stylesheets = [
    {
        'href': 'https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Mulish:wght@300;400;700&display=swap',
        'rel': 'stylesheet'
    },
    {
        'href': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
        'rel': 'stylesheet'
    }
]

# --- CSS Gradient Mappings for Legend ---
SCALE_MAPPINGS = {
    'Magma': 'linear-gradient(to right, #000004, #51127c, #b73779, #fc8961, #fcfdbf)',
    'Magma_r': 'linear-gradient(to right, #fcfdbf, #fc8961, #b73779, #51127c, #000004)',
    'Viridis': 'linear-gradient(to right, #440154, #31688e, #35b779, #fde725)',
    'Viridis_r': 'linear-gradient(to right, #fde725, #35b779, #31688e, #440154)',
    'Plasma': 'linear-gradient(to right, #0d0887, #cc4778, #f0f921)',
    'Plasma_r': 'linear-gradient(to right, #f0f921, #cc4778, #0d0887)',
    'Inferno': 'linear-gradient(to right, #000004, #57106e, #bc3754, #f98e09, #fcffa4)',
    'Inferno_r': 'linear-gradient(to right, #fcffa4, #f98e09, #bc3754, #57106e, #000004)',
    'Turbo': 'linear-gradient(to right, #30123b, #46f7f6, #a4fc3c, #e34f18, #7a0403)',
    'Turbo_r': 'linear-gradient(to right, #7a0403, #e34f18, #a4fc3c, #46f7f6, #30123b)',
    'Blues': 'linear-gradient(to right, #f7fbff, #08306b)',
    'Blues_r': 'linear-gradient(to right, #08306b, #f7fbff)',
    'Reds': 'linear-gradient(to right, #fff5f0, #67000d)',
    'Reds_r': 'linear-gradient(to right, #67000d, #fff5f0)',
    'Cividis': 'linear-gradient(to right, #002051, #797c56, #fdea45)',
    'Cividis_r': 'linear-gradient(to right, #fdea45, #797c56, #002051)',
}

# --- Global Data Manager Class (ROBUST UUID VERSION) ---
class DataManager:
    def __init__(self):
        self.layers = {} # {id: dataframe (with UUID index)}
        self.metadata = [] # [{id, name, visible, type, settings...}]
        self.original_gdf = None 
        
        # Palette for random layer colors
        self.color_cycle = ['#583CA5', '#e74c3c', '#2ecc71', '#3498db', '#9b59b6', '#f1c40f', '#e67e22', '#1abc9c']

    def add_layer(self, df, name, filename="", is_primary=False):
        layer_id = str(uuid.uuid4())
        
        # --- ROBUSTNESS: Generate Internal UUIDs ---
        # Create a new column with UUIDs and set it as the index.
        # This guarantees every row has a unique, persistent system ID.
        df = df.copy()
        df['row_uuid'] = [str(uuid.uuid4()) for _ in range(len(df))]
        df.set_index('row_uuid', inplace=True)
        
        # Ensure there is a Visible ID column for the user
        existing_id_col = next((c for c in df.columns if c.lower() in ['id', 'fid', 'name']), None)
        if not existing_id_col:
            # Create a simple visible ID if none exists
            df.insert(0, 'ID', range(1, len(df) + 1))
        
        # Detect numeric columns for coloring
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        
        # Determine defaults
        if name == "Settlements":
            def_size, def_opacity, def_color = 4, 0.8, '#FBB800'
        else:
            def_size, def_opacity, def_color = 15, 1.0, random.choice(self.color_cycle)
        
        self.layers[layer_id] = df
        self.metadata.insert(0, {
            'id': layer_id,
            'name': name if name else f"Layer {len(self.metadata)+1}",
            'filename': filename,
            'visible': True,
            'is_primary': is_primary,
            'size': def_size,
            'opacity': def_opacity,
            'color_mode': 'single', 
            'color_column': 'Single Color',
            'color_scale': 'Magma_r',
            'single_color_hex': def_color, 
            'columns': df.columns.tolist(),
            'numeric_columns': numeric_cols
        })
        return layer_id

    def move_layer(self, layer_id, direction):
        idx = next((i for i, item in enumerate(self.metadata) if item["id"] == layer_id), -1)
        if idx == -1: return
        
        if direction == 'up' and idx > 0:
            self.metadata[idx], self.metadata[idx-1] = self.metadata[idx-1], self.metadata[idx]
        elif direction == 'down' and idx < len(self.metadata) - 1:
            self.metadata[idx], self.metadata[idx+1] = self.metadata[idx+1], self.metadata[idx]

    def delete_layer(self, layer_id):
        self.metadata = [l for l in self.metadata if l['id'] != layer_id]
        if layer_id in self.layers:
            del self.layers[layer_id]

    def toggle_visibility(self, layer_id):
        for layer in self.metadata:
            if layer['id'] == layer_id:
                layer['visible'] = not layer['visible']
                break

    def update_setting(self, layer_id, key, value):
        for layer in self.metadata:
            if layer['id'] == layer_id:
                layer[key] = value
                break

    def get_df(self, layer_id):
        return self.layers.get(layer_id)

    # --- Session Management ---
    def get_session_state(self):
        serialized_layers = {}
        for lid, df in self.layers.items():
            # Index (UUID) is stored automatically by to_json(orient='split')
            serialized_layers[lid] = df.to_json(orient='split', date_format='iso')
            
        return {
            'metadata': self.metadata,
            'layers': serialized_layers,
            'version': '1.0'
        }

    def load_session_state(self, session_data):
        try:
            self.metadata = session_data.get('metadata', [])
            self.layers = {}
            for lid, df_json in session_data.get('layers', {}).items():
                df = pd.read_json(io.StringIO(df_json), orient='split')
                # Ensure the index is treated as string (UUID)
                df.index = df.index.astype(str)
                self.layers[lid] = df
            return True, "Session loaded successfully."
        except Exception as e:
            return False, f"Error loading session: {str(e)}"

# Initialize Global Manager
dm = DataManager()

def agcap_explorer(settles_gdf, default_column, figure_title):
    # --- Initial Data Processing ---
    if settles_gdf.crs is not None and settles_gdf.crs.to_string() != "EPSG:4326":
        try:
            settles_gdf = settles_gdf.to_crs(epsg=4326)
        except Exception as e:
            print(f"Warning: Could not convert CRS. Error: {e}")

    # Store original GDF (with polygons) for export
    dm.original_gdf = settles_gdf.copy()
    if dm.original_gdf.crs is None or dm.original_gdf.crs.to_string() != "EPSG:4326":
         try: dm.original_gdf = dm.original_gdf.to_crs(epsg=4326)
         except: pass

    centroids_gdf = settles_gdf.copy()
    centroids_gdf = centroids_gdf[centroids_gdf.geometry.notna()]
    centroids_gdf.geometry = centroids_gdf.geometry.centroid

    df_main = centroids_gdf.copy()
    df_main['lat'] = df_main.geometry.y
    df_main['lon'] = df_main.geometry.x
    df_main = df_main.drop(columns='geometry')

    # Initialize Custom Columns
    if 'Notes' not in df_main.columns:
        df_main['Notes'] = ""
    if 'Score' not in df_main.columns:
        df_main['Score'] = 0 # Initialize with integer 0

    # Detect Types for Filter Panel
    numeric_columns = []
    categorical_columns = []
    for col in df_main.columns:
        if col in ['Notes', 'Score']:
            continue

        if pd.api.types.is_numeric_dtype(df_main[col]):
            df_main[col] = pd.to_numeric(df_main[col], errors='coerce').astype('float64')
            numeric_columns.append(col)
        else:
            df_main[col] = df_main[col].astype(str)
            categorical_columns.append(col)
    
    all_filterable_columns = numeric_columns + categorical_columns
    if default_column not in numeric_columns and numeric_columns:
        default_column = numeric_columns[0]

    # Add Initial Layer (UUID generated inside add_layer)
    dm.layers = {}
    dm.metadata = []
    initial_id = dm.add_layer(df_main, "Settlements", is_primary=True)
    
    # Set specific color mode for main layer
    dm.update_setting(initial_id, 'color_mode', 'column')
    dm.update_setting(initial_id, 'color_column', default_column)
    dm.update_setting(initial_id, 'color_scale', 'Magma_r') 

    # Available Color Scales
    color_scales = [
        'Viridis', 'Viridis_r', 'Plasma', 'Plasma_r', 
        'Inferno', 'Inferno_r', 'Magma', 'Magma_r',
        'Cividis', 'Cividis_r', 'Blues', 'Blues_r',
        'Reds', 'Reds_r', 'Turbo', 'Turbo_r'
    ]
    
    # Basemap Options
    basemap_options = [
        {'label': 'OpenStreetMap', 'value': 'open-street-map'},
        {'label': 'Carto Positron', 'value': 'carto-positron'},
        {'label': 'Carto Dark Matter', 'value': 'carto-darkmatter'},
        {'label': 'Stamen Terrain', 'value': 'stamen-terrain'},
        {'label': 'Satellite (Mapbox Token Req.)', 'value': 'satellite'},
        {'label': 'Satellite Streets (Mapbox Token Req.)', 'value': 'satellite-streets'},
        {'label': 'Light (Mapbox Token Req.)', 'value': 'light'},
        {'label': 'Dark (Mapbox Token Req.)', 'value': 'dark'},
    ]
    
    # 1. FIND THE CORRECT ASSETS PATH
    try:
        # This works when running from scripts/app.py
        current_script_folder = os.path.dirname(os.path.abspath(__file__))
        root_project_folder = os.path.dirname(current_script_folder) # Go up from /scripts to /root
    except NameError:
        # This works when running inside the Jupyter Notebook (notebooks folder)
        import os
        current_script_folder = os.getcwd() 
        # Assuming notebook is in 'notebooks/', go up one level to root
        root_project_folder = os.path.dirname(current_script_folder)

    # Define the assets path explicitly
    assets_path = os.path.join(root_project_folder, 'assets')
    
    # Optional: Verify it exists (prints to your notebook output)
    if not os.path.exists(assets_path):
        print(f"WARNING: Assets folder not found at: {assets_path}")
    
    app = dash.Dash(__name__, external_stylesheets=external_stylesheets, assets_folder=assets_path)
    app.title = figure_title

    # ---------------- GLOBAL CSS -------------------
    app.index_string = """
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            <link rel="icon" type="image/x-icon" href="/assets/favicon.ico">
            {%css%}
            <style>
                * { box-sizing: border-box; }
                :root {
                    --brand-gold: #FBB800;
                    --brand-dark-blue: #44546A;
                    --brand-grey: #555555;
                    --brand-purple: #583CA5;
                    --brand-light: #ecf0f1;
                    --accent-contrast: #3498db;
                }
                html, body, #_dash-app-content {
                    margin: 0 !important; padding: 0 !important;
                    height: 100% !important; overflow: hidden !important;
                    font-family: 'Mulish', sans-serif;
                }
                h1, h2, h3, h4, h5, h6, .barlow-title {
                    font-family: 'Barlow Condensed', sans-serif !important;
                    text-transform: uppercase;
                }
                .js-plotly-plot, .plot-container, .modebar { margin: 0 !important; padding: 0 !important; }
                
                /* Scrollbars */
                ::-webkit-scrollbar { width: 6px; height: 6px;}
                ::-webkit-scrollbar-track { background: var(--brand-dark-blue); }
                ::-webkit-scrollbar-thumb { background: var(--brand-grey); border-radius: 3px; }
                ::-webkit-scrollbar-thumb:hover { background: var(--brand-gold); }
                
                #map-graph { width: 100%; height: 100vh; }
                
                /* --- COMPACT DROPDOWN STYLING --- */
                .Select-control {
                    background-color: var(--brand-dark-blue) !important;
                    border: 1px solid #777 !important;
                    color: white !important;
                    height: 26px !important; min-height: 26px !important;
                }
                .Select-value { line-height: 26px !important; }
                .Select-input { height: 26px !important; }
                .Select-placeholder { line-height: 26px !important; color: #aaa !important; }
                .Select-value-label { color: white !important; line-height: 26px !important; }
                .Select-menu-outer {
                    background-color: var(--brand-dark-blue) !important;
                    border: 1px solid #777 !important;
                    color: white !important;
                    margin-top: 0px !important;
                }
                .Select-option {
                    background-color: var(--brand-dark-blue) !important;
                    color: white !important;
                    padding: 4px 8px !important;
                }
                .Select-option:hover, .Select-option.is-focused {
                    background-color: var(--brand-purple) !important;
                    color: white !important;
                }
                .Select-arrow-zone { color: white !important; }
                
                input[type="text"], input[type="number"], input[type="password"] {
                    background-color: var(--brand-grey) !important;
                    border: 1px solid #777 !important;
                    color: white !important;
                    height: 26px !important;
                    font-size: 11px !important;
                }
                input[type="color"] {
                    height: 26px !important; padding: 0 !important; border: none !important;
                }

                .rc-slider-track { background-color: var(--brand-purple) !important; }
                .rc-slider-rail { background-color: #333 !important; }
                .rc-slider-handle {
                    border: 2px solid var(--brand-gold) !important;
                    background-color: var(--brand-gold) !important;
                    opacity: 1 !important;
                    width: 10px !important; height: 10px !important;
                    margin-top: -3px !important;
                }
                .rc-slider-handle:hover { border-color: white !important; }
                
                /* Table Styles */
                .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner input:not([type=radio]):not([type=checkbox]) {
                    color: white !important;
                    font-family: 'Mulish', sans-serif !important;
                }
                .dash-table-container .previous-next-container .page-number,
                .dash-table-container .previous-next-container .last-page,
                .dash-table-container .previous-next-container .first-page,
                .dash-table-container .previous-next-container .previous-page,
                .dash-table-container .previous-next-container .next-page {
                    color: var(--brand-light) !important;
                }
                .dash-table-container .previous-next-container .page-number.current-page {
                    color: var(--brand-gold) !important;
                }
                
                .sidebar-btn {
                    display: flex; align-items: center; justify-content: center;
                    width: 34px; height: 34px; margin: 15px auto;
                    border: none; border-radius: 50%;
                    background-color: transparent; color: #bdc3c7;
                    cursor: pointer; font-size: 16px; transition: all 0.2s ease;
                }
                .sidebar-btn:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                    color: var(--brand-gold); 
                    box-shadow: 0 0 8px rgba(251, 184, 0, 0.4);
                }
                
                .export {
                    background-color: var(--brand-purple) !important;
                    color: white !important;
                    border: none !important;
                    border-radius: 4px !important;
                    padding: 4px 10px !important;
                    margin-bottom: 5px !important;
                    font-family: 'Barlow Condensed', sans-serif !important;
                    font-weight: bold;
                    letter-spacing: 0.5px;
                    cursor: pointer !important;
                    font-size: 12px;
                }
                .export:hover {
                    background-color: var(--brand-gold) !important;
                    color: var(--brand-dark-blue) !important;
                }

                button { transition: all 0.3s ease; }
                
                #resize-handle {
                    width: 100%; height: 8px;
                    background-color: var(--brand-dark-blue);
                    border-top: 1px solid var(--brand-grey);
                    border-bottom: 1px solid var(--brand-grey);
                    cursor: ns-resize;
                    display: flex; justify-content: center; align-items: center;
                }
                #resize-handle::after {
                    content: "......"; color: #7f8c8d; font-size: 14px;
                    line-height: 0px; letter-spacing: 2px; margin-top: -8px; 
                }
                #resize-handle:hover { background-color: var(--brand-purple); }
                #resize-handle:hover::after { color: white; }
                
                #legend-container {
                    background: rgba(44, 62, 80, 0.85);
                    border-radius: 5px; padding: 10px;
                    max-height: 300px; overflow-y: auto;
                    color: white; font-family: 'Mulish', sans-serif;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.3);
                    backdrop-filter: blur(4px); border: 1px solid #555;
                }
                .legend-item { display: flex; align-items: center; margin-bottom: 8px; font-size: 11px; }
                .legend-marker { border-radius: 50%; margin-right: 8px; border: 1px solid white; flex-shrink: 0; }
                .legend-gradient-bar { height: 8px; width: 60px; border-radius: 2px; margin: 0 5px; border: 1px solid #ccc; flex-shrink: 0; }
                .legend-label { color: #ecf0f1; font-weight: 300; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px; }

                /* Details/Summary Styling for Analysis */
                details { margin-bottom: 10px; border: 1px solid #555; border-radius: 4px; overflow: hidden; }
                summary { padding: 8px 10px; background-color: #34495e; cursor: pointer; color: #ecf0f1; font-size: 12px; font-weight: bold; font-family: 'Barlow Condensed'; letter-spacing: 0.5px; list-style: none; display: flex; align-items: center; justify-content: space-between; }
                summary:hover { background-color: #44546A; color: #FBB800; }
                summary::-webkit-details-marker { display: none; }
                summary::after { content: '+'; font-size: 14px; font-weight: bold; }
                details[open] summary::after { content: '-'; }
                details[open] summary { border-bottom: 1px solid #555; }
                .analysis-content-inner { padding: 10px; background-color: rgba(0,0,0,0.2); }

                /* Radio Items Styling */
                .radio-group label { margin-right: 15px; color: #bdc3c7; font-size: 11px; cursor: pointer; }
                .radio-group input { margin-right: 5px; }

            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
                <script>
                    document.addEventListener('DOMContentLoaded', function() {
                        setTimeout(function() {
                            const handle = document.getElementById('resize-handle');
                            const panel = document.getElementById('table-panel');
                            if (handle && panel) {
                                let isDragging = false;
                                let startY;
                                let startHeight;

                                handle.addEventListener('mousedown', function(e) {
                                    isDragging = true;
                                    startY = e.clientY;
                                    startHeight = parseInt(window.getComputedStyle(panel).height, 10);
                                    document.body.style.cursor = 'ns-resize';
                                    e.preventDefault();
                                });

                                document.addEventListener('mousemove', function(e) {
                                    if (!isDragging) return;
                                    const dy = startY - e.clientY; 
                                    let newHeight = startHeight + dy;
                                    if (newHeight < 50) newHeight = 50;
                                    if (newHeight > window.innerHeight - 100) newHeight = window.innerHeight - 100;
                                    panel.style.height = newHeight + 'px';
                                });

                                document.addEventListener('mouseup', function() {
                                    isDragging = false;
                                    document.body.style.cursor = 'default';
                                });
                            }
                        }, 2000); 
                    });
                </script>
            </footer>
        </body>
    </html>
    """

    # --- COMPONENT SETUP ---
    sidebar_items = []
    
    # --- MODIFIED: LOGO WITH LINK ---
    sidebar_items.append(
        html.A(
            html.Img(
                src='/assets/images/logo.png', 
                style={'width': '35px', 'display': 'block', 'margin': '0 auto'}
            ),
            href="https://www.seforall.org/",
            target="_blank",  # Opens in new tab
            style={'display': 'block', 'margin': '15px auto 5px auto', 'textDecoration': 'none'}
        )
    )
    # --------------------------------
    
    sidebar_items.extend([
        # We add an ID to the buttons so we can target their style in the callback
        html.Button(html.I(className="fas fa-layer-group"), id="layers-btn", n_clicks=0, title="Layers", className="sidebar-btn"),
        html.Button(html.I(className="fas fa-sliders-h"), id="filters-btn", n_clicks=0, title="Filters", className="sidebar-btn"),
        html.Button(html.I(className="fas fa-chart-pie"), id="analysis-btn", n_clicks=0, title="Analysis", className="sidebar-btn"),
        html.A(html.I(className="fas fa-info-circle"), href="https://www.seforall.org/", target="_blank", title="Documentation", className="sidebar-btn", style={'textDecoration': 'none', 'display': 'flex'}),
    ])

    sidebar_items.extend([
        html.Div(style={'flexGrow': 1}),
        html.Button(html.I(className="fas fa-save"), id="save-session-btn", n_clicks=0, title="Save Session", className="sidebar-btn", style={'color': '#FBB800'}),
        dcc.Upload(
            id='load-session-upload',
            children=html.Div(html.I(className="fas fa-folder-open"), className="sidebar-btn", title="Load Session", style={'color': '#FBB800'}),
            multiple=False,
            style={'cursor': 'pointer'}
        )
    ])

    map_overlays = [
        dcc.Graph(id='map', style={'width': '100%', 'height': '100vh'}, config={'scrollZoom': True, 'displayModeBar': True, 'responsive': True}),
        
        # Geocoder Bar
        html.Div([
            dcc.Input(id='geocoder-input', type='text', placeholder='Search place...', style={'padding': '6px 12px', 'borderRadius': '20px 0 0 20px', 'border': 'none', 'width': '180px', 'outline': 'none', 'boxShadow': '0 2px 5px rgba(0,0,0,0.3)', 'fontFamily': 'Mulish'}),
            html.Button(html.I(className="fas fa-search"), id='geocoder-btn', n_clicks=0, style={'padding': '6px 15px', 'borderRadius': '0 20px 20px 0', 'border': 'none', 'backgroundColor': '#583CA5', 'color': 'white', 'cursor': 'pointer', 'boxShadow': '0 2px 5px rgba(0,0,0,0.3)'})
        ], style={'position': 'absolute', 'top': '15px', 'left': '50%', 'transform': 'translateX(-50%)', 'zIndex': 10, 'display': 'flex'}),
        
        # Legend Container (Moved to Top Right)
        html.Div(id='legend-container', style={'position': 'absolute', 'top': '20px', 'right': '20px', 'zIndex': 5, 'width': '220px', 'display': 'none'}),

        #Bottom right logo
        html.Img(
            src='/assets/images/logo.png',  
            style={
                'position': 'absolute',
                'bottom': '35px',  # 35px from bottom (above the footer/table handle)
                'right': '20px',   # 20px from right
                'width': '8vh',  # Adjust width as needed
                'zIndex': 5,       # Keeps it above the map tiles
                'opacity': 0.9,
                'pointerEvents': 'none' # Allows clicking through the empty parts of the png
            }
        )
    ]

    # ---------------------- LAYOUT ----------------------
    app.layout = html.Div([
        dcc.Store(id='table-state-store', data=False),
        dcc.Store(id='layer-manager-trigger', data=0),
        dcc.Store(id='map-view-store', data={'center': None, 'zoom': None}), 
        dcc.Store(id='save-status-store'),
        dcc.Download(id="download-session"), 

        # 1. Left Menu
        html.Div(sidebar_items, style={'position':'fixed','top':0,'left':0,'width':'45px','height':'100vh','backgroundColor':'#1e1e1e','zIndex':30, 'borderRight': '1px solid #333', 'display': 'flex', 'flexDirection': 'column'}),

        # 2. Left Pane
        html.Div(id="left-pane-container", children=[
            html.Div(id='left-pane', style={'width':'25vw','height':'100vh','backgroundColor':'#44546A','color':'#ecf0f1','padding':'10px','boxSizing':'border-box','boxShadow':'inset -5px 0 10px -5px rgba(0,0,0,0.5)','overflowY':'auto'}, children=[
                
                html.Div([
                    html.H2(figure_title, style={'color': '#FBB800', 'marginBottom': '0px', 'fontWeight':'700', 'letterSpacing':'1px', 'fontSize': '22px'}),
                    html.H5("Sustainable Energy for All", style={'color': '#bdc3c7', 'marginTop': '5px', 'marginBottom': '0px', 'fontWeight': '300', 'fontSize':'12px', 'fontStyle':'italic', 'fontFamily': 'Mulish'})
                ], style={'borderBottom': '1px solid #555555', 'paddingBottom': '15px', 'marginBottom': '15px', 'textAlign':'left'}),

                # --- LAYERS TAB ---
                html.Div(id='layers-content', style={'display': 'none'}, children=[
                    html.H3("Layers", style={'borderBottom':'1px solid #555555', 'paddingBottom':'5px', 'marginBottom': '10px', 'fontSize': '16px'}),
                    
                    # Basemap Settings
                    html.Div([
                        html.H4("Basemap", style={'color': '#ecf0f1', 'fontSize': '12px', 'marginBottom': '5px'}),
                        dcc.Dropdown(
                            id='basemap-dropdown',
                            options=basemap_options,
                            value='open-street-map',
                            clearable=False,
                            style={'width': '100%', 'marginBottom': '10px', 'color': '#333', 'fontSize': '11px'}
                        ),
                        dcc.Input(
                            id='mapbox-token-input',
                            type='password',
                            placeholder='Paste Mapbox Token (Optional)',
                            style={'width': '100%', 'padding': '5px', 'borderRadius': '4px', 'border': '1px solid #555555', 'backgroundColor': '#555555', 'color': 'white', 'marginBottom': '10px', 'fontSize': '11px'}
                        )
                    ], style={'marginBottom': '10px', 'borderBottom': '1px dashed #555555', 'paddingBottom': '10px'}),

                    dcc.Upload(
                        id='upload-data',
                        children=html.Button("+ Add Layer (CSV/GeoJSON/ZipShp)", style={'width':'100%','padding':'8px','border':'2px dashed #7f8c8d','background':'transparent','color':'#FBB800','borderRadius':'4px','cursor':'pointer', 'fontWeight':'bold', 'marginBottom':'10px', 'fontSize': '12px'}),
                        multiple=False
                    ),
                    html.Div(id='upload-status', style={'marginBottom':'10px', 'color':'#e74c3c', 'fontSize':'11px'}),

                    html.Div(id='layers-list-container')
                ]),

                # --- FILTERS TAB ---
                html.Div(id='filters-content', style={'display': 'block'}, children=[
                    html.H3("Filters (Primary)", style={'borderBottom':'1px solid #555555', 'paddingBottom':'5px', 'marginBottom':'15px', 'fontSize': '16px'}),
                    html.Label("Filter By", style={'fontWeight':'bold', 'color':'#FBB800', 'fontSize': '12px'}),
                    dcc.Dropdown(id='column-dropdown', options=[{'label': col, 'value': col} for col in all_filterable_columns], value=[default_column], multi=True, style={'width': '100%', 'marginBottom': '15px', 'borderRadius': '4px', 'color': '#333', 'fontSize': '11px'}),
                    html.Div(id='histograms-container')
                ]),

                # --- ANALYSIS TAB ---
                html.Div(id='analysis-content', style={'display': 'none'}, children=[
                    html.H3("Analysis", style={'borderBottom':'1px solid #555555', 'paddingBottom':'5px', 'fontSize': '16px', 'marginBottom': '15px'}),
                    
                    # 1. Data Subset Selector
                    html.Div([
                        html.Label("Analyze:", style={'color': '#FBB800', 'fontWeight': 'bold', 'fontSize': '12px', 'marginRight': '10px'}),
                        dcc.RadioItems(
                            id='analysis-subset-selector',
                            options=[
                                {'label': 'Selected', 'value': 'selected'},
                                {'label': 'Filtered', 'value': 'filtered'},
                                {'label': 'All Data', 'value': 'all'},
                            ],
                            value='selected',
                            inline=True, # <--- Horizontal Layout
                            className='radio-group',
                            style={'display': 'inline-block'}
                        )
                    ], style={'marginBottom': '15px', 'paddingBottom': '10px', 'borderBottom': '1px solid #555'}),

                    # 2. Thematic Sections
                    html.Div([
                        html.Details([
                            html.Summary("Population & Demographics"),
                            html.Div("Charts for Population & Demographics will appear here.", className="analysis-content-inner")
                        ]),
                        html.Details([
                            html.Summary("Electrification"),
                            html.Div("Charts for Electrification will appear here.", className="analysis-content-inner")
                        ]),
                        html.Details([
                            html.Summary("Economic, Livelihoods, and Risks"),
                            html.Div("Charts for Economic/Risk factors will appear here.", className="analysis-content-inner")
                        ]),
                        html.Details([
                            html.Summary("Physical Geography & Climate"),
                            html.Div("Charts for Geo/Climate will appear here.", className="analysis-content-inner")
                        ]),
                        html.Details([
                            html.Summary("Market Accessibility"),
                            html.Div("Charts for Market Access will appear here.", className="analysis-content-inner")
                        ]),
                         html.Details([
                            html.Summary("Agricultural Cooling Demand"),
                            # --- ADDED AG CHART HERE ---
                            html.Div([
                                dcc.Graph(id='spider-chart-ag', config={'displayModeBar': False}, style={'height': '200px'})
                            ], className="analysis-content-inner")
                        ], open=True),
                        html.Details([
                            html.Summary("Agriculture Production"),
                            html.Div([
                                # --- ADDED THIS DIV FOR THE TOTAL SUM ---
                                html.Div(id='prod-total-text', style={
                                    'textAlign': 'center', 
                                    'color': '#FBB800', 
                                    'fontWeight': 'bold', 
                                    'fontSize': '12px', 
                                    'marginBottom': '4px',
                                    'fontFamily': 'Barlow Condensed'
                                }),
                                # ----------------------------------------
                                dcc.Graph(id='spider-chart-prod', config={'displayModeBar': False}, style={'height': '200px'})
                            ], className="analysis-content-inner")
                        ], open=True),
                        html.Details([
                            html.Summary("Fishing Cooling Demand"),
                            # --- RENAMED FISHING CHART ID ---
                            html.Div([
                                dcc.Graph(id='spider-chart-fish', config={'displayModeBar': False}, style={'height': '200px'})
                            ], className="analysis-content-inner")
                        ], open=True), 
                    ])
                ])
            ])
        ], style={'position':'fixed','top':0,'left':'45px','height':'100vh','zIndex':20}),

        # 3. Collapse Button
        html.Button("‹", id="collapse-btn", n_clicks=0, style={'position':'fixed','top':'20px','left':'345px','zIndex':40,'width':'20px','height':'30px','backgroundColor':'#555555','color':'white','border':'none','borderTopRightRadius':'4px','borderBottomRightRadius':'4px','cursor':'pointer','fontSize':'18px','padding':'0','lineHeight':'28px'}),

        # 4. Map & Overlays
        html.Div(map_overlays, id='map-container', style={'position':'fixed', 'top':0, 'left':'345px', 'right':0, 'height':'100vh', 'zIndex':1, 'transition': 'left 0.3s ease'}),

        # 5. Table Interface
        html.Div(id='table-ui-wrapper', style={'position':'fixed', 'bottom':0, 'left':'345px', 'right':0, 'zIndex': 50, 'display': 'flex', 'flexDirection': 'column', 'justifyContent': 'flex-end', 'alignItems': 'center', 'transition': 'left 0.3s ease', 'pointerEvents': 'none'}, children=[
            # Toggle Button
            html.Button(children=[html.I(className="fas fa-table"), " Data"], id="table-toggle-btn", n_clicks=0, style={'pointerEvents': 'auto', 'marginBottom': '15px', 'padding': '8px 16px', 'borderRadius': '30px', 'border': 'none', 'backgroundColor': '#44546A', 'color': 'white', 'fontSize': '14px', 'boxShadow': '0 4px 6px rgba(0,0,0,0.3)', 'cursor': 'pointer', 'transition': 'transform 0.2s', 'fontFamily': 'Barlow Condensed', 'letterSpacing': '1px'}),
            
            # Table Panel
            html.Div(id='table-panel', style={'pointerEvents': 'auto', 'width': '100%', 'height': '0vh', 'backgroundColor': '#44546A', 'overflow': 'hidden', 'transition': 'height 0.3s ease-in-out', 'display': 'flex', 'flexDirection': 'column', 'boxShadow': '0 -4px 10px rgba(0,0,0,0.3)'}, children=[
                
                # Resizer Handle
                html.Div(id="resize-handle"),

                # Header Row
                html.Div([
                    html.Div([
                        html.Div([
                            html.Label("LAYER:", style={'color': '#FBB800', 'marginRight': '8px', 'fontSize': '12px', 'fontWeight': 'bold', 'fontFamily': 'Barlow Condensed'}),
                            dcc.Dropdown(id='table-layer-dropdown', clearable=False, style={'width': '180px', 'color': '#333', 'fontSize': '11px', 'height': '26px'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'marginRight': '20px'}),
                        
                        html.Button("Select All", id="select-all-btn", n_clicks=0, style={'marginRight': '5px', 'backgroundColor': '#583CA5', 'color': 'white', 'border': 'none', 'padding': '4px 8px', 'borderRadius': '4px', 'cursor': 'pointer', 'fontSize': '11px'}),
                        html.Button("Deselect All", id="deselect-all-btn", n_clicks=0, style={'marginRight': '15px', 'backgroundColor': '#555555', 'color': 'white', 'border': 'none', 'padding': '4px 8px', 'borderRadius': '4px', 'cursor': 'pointer', 'fontSize': '11px'}),
                    ], style={'display':'flex', 'alignItems':'center'}),
                    html.Button("×", id="close-table-btn", n_clicks=0, style={'border':'none','background':'transparent','fontSize':'20px','cursor':'pointer', 'color':'#e0e0e0'})
                ], style={'padding':'5px 15px','display':'flex','justifyContent':'space-between','alignItems':'center','borderBottom':'1px solid #555555', 'backgroundColor':'#44546A'}),
                
                # Table Content
                html.Div(id='table-content', style={'flex':'1', 'overflow':'hidden', 'padding':'0'}, children=[
                      html.Div([
                        html.I(className="fas fa-hand-pointer", style={'fontSize': '30px', 'marginBottom': '15px'}),
                        html.H3("No points selected", style={'marginBottom': '5px', 'color': '#ecf0f1'}),
                        html.P("Select data on map to view.", style={'color': '#bbb', 'fontSize': '12px'})
                      ], style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center', 'justifyContent': 'center', 'height': '100%', 'color': '#7f8c8d', 'textAlign': 'center'})
                ])
            ])
        ])
    ])

    # ---------------------- CALLBACKS ----------------------

    # --- HELPER FUNCTION FOR SPIDER CHART ---
    # NOW ACCEPTS 'agg' AND 'manual_range'
    def build_spider_figure(df, metrics, title, color, agg='mean', manual_range=None):
        # 1. Setup labels
        # Remove common prefixes to make chart readable
        labels = [m.replace('Ag Cooling Demand ', '').replace('Fish Cooling Demand ', '').replace(' production', '') for m in metrics]
        
        # 2. Calculate Values
        values = []
        if df.empty:
            values = [0] * len(metrics)
        else:
            for m in metrics:
                if m in df.columns:
                    # force numeric conversion
                    series = pd.to_numeric(df[m], errors='coerce')
                    
                    # --- Aggregation Logic ---
                    if agg == 'sum':
                        val = series.sum()
                    else:
                        val = series.mean()
                    
                    clean_val = val if not pd.isna(val) else 0
                    
                    # --- Clamping Logic ---
                    # Only clamp to 0-1 if we are in that specific mode
                    if manual_range == [0, 1]:
                        values.append(min(max(clean_val, 0), 1))
                    else:
                        # For production sums, we don't clamp to 1
                        values.append(clean_val if clean_val > 0 else 0)
                else:
                    values.append(0)

        # 3. Close the loop for Radar Chart
        values.append(values[0])
        labels.append(labels[0])

        # 4. Determine Axis Range
        if manual_range:
            # Fixed range (e.g. 0 to 1)
            axis_config = dict(visible=True, range=manual_range, tickfont=dict(color='#bdc3c7', size=8), gridcolor='#555')
        else:
            # Auto range (Max value + 10% buffer)
            top_val = max(values) if values else 10
            limit = top_val * 1.1 if top_val > 0 else 10
            axis_config = dict(visible=True, range=[0, limit], tickfont=dict(color='#bdc3c7', size=8), gridcolor='#555')

        # 5. Create Figure
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=labels,
            fill='toself',
            name=title,
            line_color=color,
            fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (0.4,)}" 
        ))

        fig.update_layout(
            polar=dict(
                radialaxis=axis_config,
                angularaxis=dict(tickfont=dict(color='#ecf0f1', size=10), gridcolor='#555', rotation=90),
                bgcolor='rgba(0,0,0,0)'
            ),
            showlegend=False,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=35, r=35, t=20, b=20),
            font=dict(family='Mulish', color='#ecf0f1')
        )
        return fig

    # --- UPDATED CALLBACK ---
    @app.callback(
        [Output('spider-chart-ag', 'figure'),
         Output('spider-chart-fish', 'figure'),
         Output('spider-chart-prod', 'figure'),
         Output('prod-total-text', 'children')], # <--- 1. NEW OUTPUT ADDED HERE
        Input('analysis-subset-selector', 'value'),
        Input('layer-manager-trigger', 'data'),
        Input('table-layer-dropdown', 'value'),
        Input({'type': 'histogram-slider', 'column': ALL}, 'value'), 
        State({'type': 'histogram-slider', 'column': ALL}, 'id'),
        Input({'type': 'categorical-dropdown', 'column': ALL}, 'value'), 
        State({'type': 'categorical-dropdown', 'column': ALL}, 'id'),
        Input('map', 'selectedData'),
        Input('map', 'clickData')
    )
    def update_spider_charts(subset_mode, trigger, active_layer_id, slider_vals, slider_ids, cat_vals, cat_ids, selected_data, click_data):
        # 1. Base Data Retrieval
        empty_fig = go.Figure()
        empty_fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis={'visible':False}, yaxis={'visible':False})
        
        # Default text if no data
        empty_text = "Total perishable agriculture production (t/y) 0"

        if not active_layer_id or active_layer_id not in dm.layers:
            return empty_fig, empty_fig, empty_fig, empty_text
        
        df = dm.layers[active_layer_id].copy()
        layer_meta = next((l for l in dm.metadata if l['id'] == active_layer_id), None)
        is_primary = layer_meta.get('is_primary', False) if layer_meta else False

        # 2. Filter Application (Keep your existing logic exactly as is)
        if subset_mode in ['filtered', 'selected']:
            if is_primary:
                if slider_ids and slider_vals:
                    for value, sid in zip(slider_vals, slider_ids):
                        col = sid['column']
                        if col in df.columns and value: 
                            df = df[(df[col]>=value[0]) & (df[col]<=value[1])]
                if cat_ids:
                    for values, cid in zip(cat_vals, cat_ids):
                        col = cid['column']
                        if col in df.columns and values: 
                            df = df[df[col].isin(values)]
        
        # 3. Selection Application (Keep your existing logic exactly as is)
        if subset_mode == 'selected':
            uuids = []
            if selected_data and 'points' in selected_data:
                for p in selected_data['points']:
                    if p.get('customdata') and p['customdata'][3] == active_layer_id:
                        uuids.append(p['customdata'][0])
            elif click_data and 'points' in click_data:
                p = click_data['points'][0]
                if p.get('customdata') and p['customdata'][3] == active_layer_id:
                      uuids.append(p['customdata'][0])
            
            if uuids:
                df = df[df.index.isin(uuids)]
            else:
                df = df.iloc[0:0] 

        # 4. Define Metrics
        ag_metrics = [
            'Ag Cooling Demand Export Market', 'Ag Cooling Demand National Market',
            'Ag Cooling Demand Fresh Markets', 'Ag Cooling Demand ALL Markets'
        ]

        fish_metrics = [
            'Fish Cooling Demand Export Market', 'Fish Cooling Demand National Market',
            'Fish Cooling Demand Fresh Markets', 'Fish Cooling Demand ALL Markets'
        ]

        # Production Metrics
        prod_metrics = [
            'Banana production', 'Cassava production', 'Citrus production',
            'Cowpea production', 'Other Roots production', 'Other Tropical Fruit production',
            'Other Vegetables production', 'Potato production', 'Sweet Potato production',
            'Temperate Fruit production', 'Tomato production'
        ]

        # --- 5. CALCULATE TOTAL PRODUCTION SUM (NEW LOGIC) ---
        total_prod = 0
        if not df.empty:
            # Select only the production columns that exist in the dataframe
            valid_prod_cols = [c for c in prod_metrics if c in df.columns]
            # Convert to numeric (coerce errors to NaN), fill NaN with 0, then sum all values
            total_prod = df[valid_prod_cols].apply(pd.to_numeric, errors='coerce').fillna(0).sum().sum()
        
        # Format with commas (e.g., 1,234,567)
        prod_text = f"Total perishable agriculture production (t/y) {total_prod:,.0f}"

        # 6. Generate Figures
        fig_ag = build_spider_figure(df, ag_metrics, "Ag Demand", "#FBB800", agg='mean', manual_range=[0,1])
        fig_fish = build_spider_figure(df, fish_metrics, "Fish Demand", "#3498db", agg='mean', manual_range=[0,1])
        fig_prod = build_spider_figure(df, prod_metrics, "Production", "#2ecc71", agg='sum', manual_range=None)

        return fig_ag, fig_fish, fig_prod, prod_text

    # --- NEW: AUTO-SWITCH TABLE LAYER ON MAP CLICK ---
    @app.callback(
        Output('table-layer-dropdown', 'value', allow_duplicate=True),
        Input('map', 'clickData'),
        prevent_initial_call=True
    )
    def switch_layer_on_map_click(click_data):
        if not click_data or 'points' not in click_data:
            return dash.no_update
        
        # Extract Layer ID from customdata[3]
        try:
            clicked_point = click_data['points'][0]
            # customdata structure: [Row_UUID, ColorVal, VisibleID, LayerID]
            layer_id = clicked_point['customdata'][3]
            return layer_id
        except Exception:
            return dash.no_update

    # --- SAVE SESSION CALLBACK ---
    @app.callback(
        Output("download-session", "data"),
        Input("save-session-btn", "n_clicks"),
        State("map-view-store", "data"),
        State("column-dropdown", "value"),
        prevent_initial_call=True
    )
    def save_session(n_clicks, map_view, filter_columns):
        if not n_clicks: return dash.no_update
        session_data = dm.get_session_state()
        session_data['map_view'] = map_view
        session_data['filter_columns'] = filter_columns
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"agcap_session_{timestamp}.json"
        return dict(content=json.dumps(session_data), filename=filename)

    # --- LOAD SESSION CALLBACK ---
    @app.callback(
        [Output('layer-manager-trigger', 'data', allow_duplicate=True),
         Output('map-view-store', 'data', allow_duplicate=True),
         Output('column-dropdown', 'value')],
        Input('load-session-upload', 'contents'),
        prevent_initial_call=True
    )
    def load_session(contents):
        if not contents: return dash.no_update, dash.no_update, dash.no_update
        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            session_data = json.loads(decoded.decode('utf-8'))
            
            success, msg = dm.load_session_state(session_data)
            if not success:
                print(msg)
                return dash.no_update, dash.no_update, dash.no_update
            
            map_view = session_data.get('map_view', {'center': None, 'zoom': None})
            filter_columns = session_data.get('filter_columns', [])
            return np.random.randint(100000), map_view, filter_columns
            
        except Exception as e:
            print(f"Error parsing session file: {e}")
            return dash.no_update, dash.no_update, dash.no_update

    # --- DATA PERSISTENCE (UPDATED FOR UUID) ---
    @app.callback(
        Output('save-status-store', 'data'),
        Input({'type': 'table-export', 'index': ALL}, 'data'),
        prevent_initial_call=True
    )
    def save_table_changes(rows_list):
        rows = rows_list[0] if rows_list else None
        if not rows: return dash.no_update
        
        # We search across all layers to find matching UUIDs
        for row in rows:
            uuid_idx = row.get('orig_uuid')
            if not uuid_idx: continue
            
            for lid, df in dm.layers.items():
                if uuid_idx in df.index:
                    if 'Notes' in row: 
                        df.at[uuid_idx, 'Notes'] = row.get('Notes', '')
                    if 'Score' in row:
                        val = row.get('Score')
                        try: 
                            df.at[uuid_idx, 'Score'] = int(val) if val is not None and val != '' else 0
                        except: 
                            df.at[uuid_idx, 'Score'] = 0
                    break 
        return dash.no_update

    # --- UPDATED: MANAGE TABS AND BUTTON HIGHLIGHTS ---
    @app.callback(
        [Output('layers-content', 'style'), 
         Output('filters-content', 'style'), 
         Output('analysis-content', 'style'),
         Output('layers-btn', 'style'),      # <--- New Output
         Output('filters-btn', 'style'),     # <--- New Output
         Output('analysis-btn', 'style')],   # <--- New Output
        [Input('layers-btn', 'n_clicks'), 
         Input('filters-btn', 'n_clicks'), 
         Input('analysis-btn', 'n_clicks')]
    )
    def switch_tab(btn1, btn2, btn3):
        ctx = callback_context
        
        # 1. Define Styles
        # Active: Gold + Glow
        active_style = {'color': '#FBB800', 'boxShadow': '0 0 8px rgba(251, 184, 0, 0.4)'}
        # Inactive: Standard Grey
        inactive_style = {'color': '#bdc3c7', 'boxShadow': 'none'}
        
        # 2. Determine Trigger
        if not ctx.triggered:
            # Default State: Filters tab active
            return (
                {'display': 'none'}, {'display': 'block'}, {'display': 'none'}, # Content
                inactive_style, active_style, inactive_style                    # Buttons
            )

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # 3. Return Logic (Content Styles + Button Styles)
        if button_id == 'layers-btn':
            return (
                {'display': 'block'}, {'display': 'none'}, {'display': 'none'}, # Content
                active_style, inactive_style, inactive_style                    # Buttons
            )
        elif button_id == 'analysis-btn':
            return (
                {'display': 'none'}, {'display': 'none'}, {'display': 'block'}, # Content
                inactive_style, inactive_style, active_style                    # Buttons
            )
        else: # Default or 'filters-btn'
            return (
                {'display': 'none'}, {'display': 'block'}, {'display': 'none'}, # Content
                inactive_style, active_style, inactive_style                    # Buttons
            )

    # --- UPLOAD PARSING ---
    @app.callback(
        Output('layer-manager-trigger', 'data'),
        Output('upload-status', 'children'),
        Input('upload-data', 'contents'),
        State('upload-data', 'filename'),
        State('layer-manager-trigger', 'data'),
        prevent_initial_call=True
    )
    def parse_upload(contents, filename, trigger):
        if contents is None: return dash.no_update, ""
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        try:
            new_df = None
            if 'csv' in filename.lower():
                try: df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
                except: return dash.no_update, "Error reading CSV content."
                wkt_col = next((c for c in df.columns if c.lower() in ['wkt', 'wkt_geom', 'geometry', 'geom']), None)
                lat_col = next((c for c in df.columns if c.lower() in ['lat', 'latitude', 'y']), None)
                lon_col = next((c for c in df.columns if c.lower() in ['lon', 'longitude', 'x']), None)
                if wkt_col:
                    try:
                        df[wkt_col] = df[wkt_col].astype(str)
                        geometry = df[wkt_col].apply(wkt.loads)
                        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
                        gdf['geometry'] = gdf.geometry.centroid
                        new_df = pd.DataFrame(gdf.drop(columns='geometry'))
                        new_df['lat'] = gdf.geometry.y
                        new_df['lon'] = gdf.geometry.x
                    except Exception as e: return dash.no_update, f"Error processing WKT: {str(e)}"
                elif lat_col and lon_col:
                    new_df = df
                    new_df['lat'] = new_df[lat_col]
                    new_df['lon'] = new_df[lon_col]
                else: return dash.no_update, "Error: CSV must contain lat/lon columns or a WKT geometry column."
            else:
                suffix = "." + filename.split('.')[-1]
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(decoded)
                    tmp_path = tmp.name
                try:
                    if filename.lower().endswith('.zip'): gdf = gpd.read_file(f"zip://{tmp_path}")
                    else: gdf = gpd.read_file(tmp_path)
                    if hasattr(gdf, 'crs') and gdf.crs and gdf.crs.to_string() != "EPSG:4326": gdf = gdf.to_crs(epsg=4326)
                    if hasattr(gdf, 'geometry'):
                          gdf['geometry'] = gdf.geometry.centroid
                          new_df = pd.DataFrame(gdf.drop(columns='geometry'))
                          new_df['lat'] = gdf.geometry.y
                          new_df['lon'] = gdf.geometry.x
                    else: return dash.no_update, "Error: File has no geometry."
                except Exception as e: return dash.no_update, f"Error reading geo file: {str(e)}"
                finally:
                    if os.path.exists(tmp_path): os.remove(tmp_path)
            
            if new_df is not None:
                for col in new_df.columns:
                    if pd.api.types.is_numeric_dtype(new_df[col]):
                        new_df[col] = pd.to_numeric(new_df[col], errors='coerce').astype('float64')
                    else: new_df[col] = new_df[col].astype(str)
                dm.add_layer(new_df, filename.split('.')[0], filename)
                return trigger + 1, ""
        except Exception as e: return dash.no_update, f"Error: {str(e)}"
        return dash.no_update, ""

    # --- GEOCODER ---
    @app.callback(
        Output('map-view-store', 'data', allow_duplicate=True),
        Input('geocoder-btn', 'n_clicks'),
        Input('geocoder-input', 'n_submit'),
        State('geocoder-input', 'value'),
        prevent_initial_call=True
    )
    def geocode_location(n_clicks, n_submit, query):
        if not query: return dash.no_update
        try:
            headers = {'User-Agent': 'DashAgCAP'}
            url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
            r = requests.get(url, headers=headers)
            if r.status_code == 200 and r.json():
                res = r.json()[0]
                lat, lon = float(res['lat']), float(res['lon'])
                return {'center': {'lat': lat, 'lon': lon}, 'zoom': 11}
        except: pass
        return dash.no_update

    # --- UPDATE UI ON COLOR CHANGE ---
    @app.callback(
        Output('layer-manager-trigger', 'data', allow_duplicate=True),
        Input({'type': 'layer-color-col', 'index': ALL}, 'value'),
        State('layer-manager-trigger', 'data'),
        prevent_initial_call=True
    )
    def update_layer_ui_on_color_change(values, current_trigger):
        ctx = callback_context
        if not ctx.triggered: return dash.no_update
        try:
            trigger_id_str = ctx.triggered[0]['prop_id'].split('.')[0]
            trigger_val = ctx.triggered[0]['value']
            trigger_dict = json.loads(trigger_id_str)
            l_id = trigger_dict['index']
            
            dm.update_setting(l_id, 'color_column', trigger_val)
            new_mode = 'single' if trigger_val == 'Single Color' else 'column'
            dm.update_setting(l_id, 'color_mode', new_mode)
            
            return current_trigger + 1
        except: return dash.no_update

    # --- RENDER LAYERS ---
    @app.callback(
        Output('layers-list-container', 'children'),
        Input('layer-manager-trigger', 'data')
    )
    def render_layer_list(trigger):
        children = []
        for i, layer in enumerate(dm.metadata):
            lid = layer['id']
            
            dropdown = dcc.Dropdown(
                id={'type': 'layer-color-col', 'index': lid},
                options=[{'label': c, 'value': c} for c in layer.get('numeric_columns', [])] + [{'label': 'Single Color', 'value': 'Single Color'}],
                value=layer.get('color_column'),
                clearable=False,
                style={'color':'#333', 'fontSize':'11px', 'width':'100%', 'marginTop':'0px'}
            )

            if layer['color_mode'] == 'single':
                secondary = dcc.Input(
                    id={'type': 'layer-single-color', 'index': lid}, 
                    type='color', 
                    value=layer.get('single_color_hex', '#FBB800'),
                    style={'width':'100%', 'height':'24px', 'marginTop':'0px', 'border':'none', 'padding':'0', 'backgroundColor':'transparent', 'cursor':'pointer'}
                )
            else:
                secondary = html.Div([
                    html.Label("Scale", style={'fontSize':'9px', 'color':'#bdc3c7'}),
                    dcc.Dropdown(
                        id={'type': 'layer-colorscale', 'index': lid},
                        options=[{'label': c, 'value': c} for c in color_scales],
                        value=layer.get('color_scale', 'Magma_r'),
                        clearable=False,
                        style={'color':'#333', 'fontSize':'11px', 'width':'100%'}
                    )
                ])

            card = html.Div([
                html.Div([
                    dcc.Input(id={'type': 'layer-name', 'index': lid}, value=layer['name'], style={'backgroundColor':'transparent', 'border':'none', 'color':'white', 'fontWeight':'bold', 'flexGrow': 1, 'width':'80px', 'fontSize':'12px', 'fontFamily':'Mulish'}),
                    
                    html.Button("▲", id={'type': 'layer-up', 'index': lid}, style={'padding':'0 4px', 'background':'transparent', 'border':'none', 'color':'#bdc3c7', 'cursor':'pointer', 'fontSize':'10px'}),
                    html.Button("▼", id={'type': 'layer-down', 'index': lid}, style={'padding':'0 4px', 'background':'transparent', 'border':'none', 'color':'#bdc3c7', 'cursor':'pointer', 'fontSize':'10px'}),
                    html.Button(html.I(className="fas fa-eye" if layer['visible'] else "fas fa-eye-slash", style={'color':'#2ecc71' if layer['visible'] else '#95a5a6'}), id={'type': 'layer-vis-btn', 'index': lid}, style={'background':'transparent', 'border':'none', 'cursor':'pointer', 'padding':'0 4px', 'fontSize':'12px'}),
                    html.Button(html.I(className="fas fa-trash-alt", style={'color':'#e74c3c'}), id={'type': 'layer-del-btn', 'index': lid}, style={'background':'transparent', 'border':'none', 'cursor':'pointer', 'padding':'0 4px', 'fontSize':'12px'}),
                ], style={'display':'flex','alignItems':'center','marginBottom':'2px'}),
                
                html.Div([
                    html.Div([html.Label("Size", style={'fontSize':'10px', 'color':'#bdc3c7'}), dcc.Slider(id={'type': 'layer-size', 'index': lid}, min=1, max=20, step=1, value=layer.get('size', 4), marks=None)], style={'marginBottom':'0px', 'height': '24px'}),
                    html.Div([html.Label("Opacity", style={'fontSize':'10px', 'color':'#bdc3c7'}), dcc.Slider(id={'type': 'layer-opacity', 'index': lid}, min=0, max=1, step=0.1, value=layer.get('opacity', 0.8), marks=None)], style={'marginBottom':'2px', 'height': '24px'}),
                    html.Div([html.Label("Color", style={'fontSize':'10px', 'color':'#bdc3c7'}), dropdown, secondary])
                ], style={'backgroundColor':'#34495e', 'padding':'2px 5px', 'borderRadius':'4px'})
            ], style={'padding':'5px','backgroundColor':'#555555','borderRadius':'4px','marginBottom':'5px', 'borderLeft': f"4px solid {'#2ecc71' if layer['visible'] else '#95a5a6'}"})
            children.append(card)
        return children

    # --- MANAGE LAYERS ---
    @app.callback(
        Output('layer-manager-trigger', 'data', allow_duplicate=True),
        Input({'type': 'layer-up', 'index': ALL}, 'n_clicks'),
        Input({'type': 'layer-down', 'index': ALL}, 'n_clicks'),
        Input({'type': 'layer-vis-btn', 'index': ALL}, 'n_clicks'),
        Input({'type': 'layer-del-btn', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def manage_layers(up, down, vis, delete):
        ctx = callback_context
        if not ctx.triggered: return dash.no_update
        try:
            payload = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
            layer_id = payload['index']
            action = payload['type']
            if action == 'layer-up': dm.move_layer(layer_id, 'up')
            elif action == 'layer-down': dm.move_layer(layer_id, 'down')
            elif action == 'layer-vis-btn': dm.toggle_visibility(layer_id)
            elif action == 'layer-del-btn': dm.delete_layer(layer_id)
            return np.random.randint(100000)
        except: return dash.no_update

    @app.callback(
        Output('table-layer-dropdown', 'options'),
        Output('table-layer-dropdown', 'value'),
        Input('layer-manager-trigger', 'data'),
        State('table-layer-dropdown', 'value')
    )
    def update_table_dropdown_options(trigger, current_val):
        if not dm.metadata: return [], None
        options = [{'label': l['name'], 'value': l['id']} for l in dm.metadata]
        existing_ids = [l['id'] for l in dm.metadata]
        if current_val in existing_ids: return options, current_val
        primary = next((l for l in dm.metadata if l.get('is_primary')), None)
        default_val = primary['id'] if primary else dm.metadata[0]['id']
        return options, default_val

    # --- DRAW MAP & UPDATE LEGEND (ROBUST + MANUAL HIGHLIGHTING) ---
    @app.callback(
        [Output('map', 'figure'), Output('legend-container', 'children'), Output('legend-container', 'style')],
        Input('layer-manager-trigger', 'data'),
        Input({'type': 'layer-size', 'index': ALL}, 'value'),
        Input({'type': 'layer-opacity', 'index': ALL}, 'value'),
        Input({'type': 'layer-color-col', 'index': ALL}, 'value'),
        Input({'type': 'layer-colorscale', 'index': ALL}, 'value'),
        Input({'type': 'layer-single-color', 'index': ALL}, 'value'),
        Input({'type': 'histogram-slider', 'column': ALL}, 'value'),
        State({'type': 'histogram-slider', 'column': ALL}, 'id'),
        Input({'type': 'categorical-dropdown', 'column': ALL}, 'value'),
        State({'type': 'categorical-dropdown', 'column': ALL}, 'id'),
        Input('table-layer-dropdown', 'value'),
        Input('basemap-dropdown', 'value'),
        Input('mapbox-token-input', 'value'),
        Input('map-view-store', 'data'),
        Input('map', 'selectedData'),  
        Input('map', 'clickData'),
        Input('deselect-all-btn', 'n_clicks'),  # <-- ADDED FOR OPACITY RESET
        State('map', 'relayoutData')
    )
    def update_map_multi(trigger, sizes, opacities, color_cols, color_scales, single_colors, slider_vals, slider_ids, cat_vals, cat_ids, active_table_layer, basemap_style, mapbox_token, map_view, selected_data, click_data, deselect_clicks, relayout_data):
        ctx = callback_context
        trigger_id = ctx.triggered[0]['prop_id'] if ctx.triggered else ''
        
        # --- 1. HANDLE SETTING UPDATES ---
        if ctx.triggered and 'layer-manager-trigger' not in ctx.triggered[0]['prop_id']:
            try:
                prop = ctx.triggered[0]['prop_id']
                if 'layer-' in prop and 'index' in prop:
                    trigger_dict = json.loads(prop.split('.')[0])
                    l_id = trigger_dict['index']
                    t_type = trigger_dict['type']
                    val = ctx.triggered[0]['value']
                    if t_type == 'layer-size': dm.update_setting(l_id, 'size', val)
                    elif t_type == 'layer-opacity': dm.update_setting(l_id, 'opacity', val)
                    elif t_type == 'layer-color-col':
                        dm.update_setting(l_id, 'color_column', val)
                        dm.update_setting(l_id, 'color_mode', 'single' if val == 'Single Color' else 'column')
                    elif t_type == 'layer-colorscale': dm.update_setting(l_id, 'color_scale', val)
                    elif t_type == 'layer-single-color': dm.update_setting(l_id, 'single_color_hex', val)
            except: pass

        # --- 2. IDENTIFY SELECTED POINTS (THE FIX) ---
        selected_uuids = set()
        
        # If Deselect All was clicked, we intentionally keep selected_uuids empty
        if 'deselect-all-btn' in trigger_id:
            pass # Skip populating selected_uuids, effectively resetting opacity
        else:
            # Check Box/Lasso Selection
            if selected_data and 'points' in selected_data:
                for p in selected_data['points']:
                    if 'customdata' in p:
                        selected_uuids.add(p['customdata'][0]) 
            
            # Check Single Click (Prioritize click if it just happened)
            if 'clickData' in trigger_id and click_data and 'points' in click_data:
                if 'customdata' in click_data['points'][0]:
                    selected_uuids.add(click_data['points'][0]['customdata'][0])

        data_traces = []
        legend_items = [html.H5("LEGEND", style={'fontSize': '12px', 'marginBottom': '8px', 'borderBottom': '1px solid #777', 'paddingBottom': '4px'})]
        
        visible_layers = [l for l in reversed(dm.metadata) if l['visible']]
        if not visible_layers:
             return dash.no_update, [], {'display': 'none'}

        # --- 3. BUILD TRACES ---
        for layer in visible_layers:
            dff = dm.layers[layer['id']]
            
            # Filter Primary Layer
            if layer.get('is_primary', False):
                filtered_df = dff.copy()
                if slider_ids and slider_vals:
                    for value, sid in zip(slider_vals, slider_ids):
                        col = sid['column']
                        if col in filtered_df.columns and value:
                            filtered_df = filtered_df[(filtered_df[col] >= value[0]) & (filtered_df[col] <= value[1])]
                if cat_ids and cat_vals:
                    for values, cid in zip(cat_vals, cat_ids):
                        col = cid['column']
                        if col in filtered_df.columns and values:
                            filtered_df = filtered_df[filtered_df[col].isin(values)]
                dff = filtered_df
            
            # Data Prep (Fixing float IDs)
            possible_ids = [c for c in dff.columns if c.lower() in ['id', 'fid', 'name']]
            vis_id_col = possible_ids[0] if possible_ids else dff.columns[0]
            # Convert to string and remove .0 ending
            id_values = dff[vis_id_col].astype(str).str.replace(r'\.0$', '', regex=True)

            # Customdata Prep
            # [0] UUID, [1] ColorVal, [2] VisibleID, [3] LayerID
            color_data = dff[layer['color_column']] if layer['color_mode']!='single' and layer['color_column'] in dff else [0]*len(dff)
            layer_id_list = [layer['id']] * len(dff)
            
            custom_data_stack = np.stack((dff.index, color_data, id_values, layer_id_list), axis=-1)

            # --- CALCULATE STYLES (MANUAL HIGHLIGHTING) ---
            base_size = layer['size']
            base_opacity = layer.get('opacity', 0.8)
            
            # Default Arrays
            size_array = np.full(len(dff), base_size)
            opacity_array = np.full(len(dff), base_opacity)
            
            # Apply Highlighting ONLY if this is the active layer
            if layer['id'] == active_table_layer and selected_uuids:
                # Boolean mask for selected rows
                mask = dff.index.isin(selected_uuids)
                
                # Apply: Selected = Bigger/Opaque, Unselected = Normal/Dimmer
                size_array = np.where(mask, base_size + 6, base_size)
                opacity_array = np.where(mask, 1.0, base_opacity * 0.5)

            # Legend & Marker Setup
            if layer['color_mode'] == 'single':
                color_val = layer.get('single_color_hex', '#FBB800')
                marker_dict = dict(size=size_array, color=color_val, opacity=opacity_array)
                hover_str = f"<b>{layer['name']}</b><br>ID: %{{customdata[2]}}"
                
                legend_items.append(html.Div([
                    html.Div(className="legend-marker", style={'backgroundColor': color_val, 'width': f"{base_size}px", 'height': f"{base_size}px"}),
                    html.Div(layer['name'], className="legend-label")
                ], className="legend-item"))
                
            else:
                col = layer['color_column']
                scale_name = layer.get('color_scale', 'Magma_r')
                if col in dff.columns:
                    marker_dict = dict(
                        size=size_array, color=dff[col], colorscale=scale_name,
                        showscale=False, opacity=opacity_array
                    )
                    hover_str = f"<b>{layer['name']}</b><br>ID: %{{customdata[2]}}<br>{col}: %{{customdata[1]}}"
                    
                    grad_css = SCALE_MAPPINGS.get(scale_name, 'linear-gradient(to right, #ccc, #333)')
                    mn, mx = dff[col].min(), dff[col].max()
                    
                    # Update Legend Text to include Column Name
                    legend_label_text = f"{layer['name']} ({col})"

                    legend_items.append(html.Div([
                        html.Div(legend_label_text, style={'fontWeight':'bold', 'fontSize':'10px', 'marginBottom':'2px'}),
                        html.Div([
                            html.Span(f"{mn:.1f}", style={'fontSize':'9px', 'marginRight':'3px'}),
                            html.Div(className="legend-gradient-bar", style={'background': grad_css}),
                            html.Span(f"{mx:.1f}", style={'fontSize':'9px', 'marginLeft':'3px'})
                        ], style={'display':'flex', 'alignItems':'center'})
                    ], style={'marginBottom': '8px'}))
                else:
                    marker_dict = dict(size=base_size, color='gray')
                    hover_str = "Error: Col missing"

            trace = go.Scattermapbox(
                lat=dff['lat'], lon=dff['lon'], mode='markers', marker=marker_dict,
                customdata=custom_data_stack,
                hovertemplate=hover_str + "<extra></extra>"
            )

            # Disable native Plotly selection visual (since we did it manually)
            trace.selected = dict(marker=dict(opacity=1.0))
            trace.unselected = dict(marker=dict(opacity=1.0))

            data_traces.append(trace)

        # --- 4. VIEW SETTINGS ---
        center, zoom = dict(lat=0, lon=0), 5
        if ctx.triggered and 'map-view-store' in ctx.triggered[0]['prop_id'] and map_view['center']:
            center, zoom = map_view['center'], map_view['zoom']
        elif relayout_data and 'mapbox.center' in relayout_data:
            center, zoom = relayout_data['mapbox.center'], relayout_data['mapbox.zoom']
        else:
            if dm.metadata:
                prim = next((l for l in dm.metadata if l.get('is_primary')), dm.metadata[0])
                dff_c = dm.layers[prim['id']]
                if not dff_c.empty: center = dict(lat=dff_c.lat.mean(), lon=dff_c.lon.mean())

        fig = go.Figure(data=data_traces)
        fig.update_layout(
            mapbox_style=basemap_options[0]['value'] if not basemap_style else basemap_style,
            mapbox_accesstoken=mapbox_token if mapbox_token else None,
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            clickmode='event+select', mapbox=dict(center=center, zoom=zoom),
            paper_bgcolor='#44546A', plot_bgcolor='#44546A', showlegend=False
        )
        
        # Legend Moved to Top Right
        legend_style = {'display': 'block', 'position': 'absolute', 'top': '50px', 'right': '20px', 'zIndex': 5, 'width': '220px', 'maxHeight': '80vh', 'overflowY': 'auto'}
        
        return fig, legend_items, legend_style

    # --- FILTERS PANEL ---
    @app.callback(
        Output('histograms-container', 'children'),
        Input('column-dropdown', 'value'),
        State({'type': 'histogram-slider', 'column': ALL}, 'value'),
        State({'type': 'histogram-slider', 'column': ALL}, 'id'),
        State({'type': 'categorical-dropdown', 'column': ALL}, 'value'),
        State({'type': 'categorical-dropdown', 'column': ALL}, 'id')
    )
    def update_filter_panel(selected_columns, slider_vals, slider_ids, cat_vals, cat_ids):
        if not selected_columns: return []
        current_numeric, current_cat = {}, {}
        if slider_ids: current_numeric = {id_dict['column']: val for id_dict, val in zip(slider_ids, slider_vals)}
        if cat_ids: current_cat = {id_dict['column']: val for id_dict, val in zip(cat_ids, cat_vals)}
        children = []
        for col in selected_columns:
            if col in ['Notes', 'Score']: continue
            if pd.api.types.is_numeric_dtype(df_main[col]):
                clean = df_main[col].dropna()
                mn, mx = (clean.min(), clean.max()) if not clean.empty else (0, 1)
                val = current_numeric.get(col, [mn, mx])
                fig = go.Figure(go.Histogram(x=clean, marker_color='#FBB800'))
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#ecf0f1'), xaxis=dict(showgrid=False,showticklabels=False), yaxis=dict(showgrid=False,visible=False), height=50)
                children.append(html.Div([
                    html.Label(col, style={'fontSize':'11px','fontWeight':'bold', 'color': '#ecf0f1', 'fontFamily': 'Mulish'}),
                    html.Div([dcc.Input(id={'type': 'min-input', 'column': col}, type='number', value=val[0], style={'width':'45%','backgroundColor':'#333333','color':'#ecf0f1','border':'1px solid #777', 'fontSize':'10px'}), dcc.Input(id={'type': 'max-input', 'column': col}, type='number', value=val[1], style={'width':'45%','backgroundColor':'#333333','color':'#ecf0f1','border':'1px solid #777', 'fontSize':'10px'})], style={'display':'flex','justifyContent':'space-between'}),
                    dcc.Graph(figure=fig, style={'height':'50px'}, config={'staticPlot':True}),
                    dcc.RangeSlider(id={'type': 'histogram-slider', 'column': col}, min=mn, max=mx, value=val, tooltip={"always_visible": False})
                ], style={'marginBottom':'10px','backgroundColor':'#333333','padding':'8px','borderRadius':'5px'}))
            else:
                uniq = sorted(df_main[col].dropna().unique().tolist())
                children.append(html.Div([html.Label(col, style={'fontSize':'11px','fontWeight':'bold', 'color': '#ecf0f1', 'fontFamily': 'Mulish'}), dcc.Dropdown(id={'type': 'categorical-dropdown', 'column': col}, options=[{'label':str(v),'value':str(v)} for v in uniq], value=current_cat.get(col, []), multi=True, style={'color':'#333', 'fontSize': '10px'})], style={'marginBottom':'10px','backgroundColor':'#333333','padding':'8px','borderRadius':'5px'}))
        return children

    @app.callback(Output({'type': 'histogram-slider', 'column': ALL}, 'value'), Input({'type': 'min-input', 'column': ALL}, 'value'), Input({'type': 'max-input', 'column': ALL}, 'value'), State({'type': 'histogram-slider', 'column': ALL}, 'value'), State({'type': 'histogram-slider', 'column': ALL}, 'min'), State({'type': 'histogram-slider', 'column': ALL}, 'max'))
    def update_sliders(min_inputs, max_inputs, current_vals, mins, maxs):
        if not callback_context.triggered: return [dash.no_update]*len(current_vals)
        return [[max(mins[i], min_inputs[i] if min_inputs[i] is not None else v[0]), min(maxs[i], max_inputs[i] if max_inputs[i] is not None else v[1])] for i, v in enumerate(current_vals)]

    @app.callback(Output({'type': 'min-input', 'column': ALL}, 'value'), Output({'type': 'max-input', 'column': ALL}, 'value'), Input({'type': 'histogram-slider', 'column': ALL}, 'value'))
    def update_inputs(vals): return [round(v[0],3) for v in vals], [round(v[1],3) for v in vals]

    # --- TABLE UPDATE (UPDATED FOR UUID & SANITIZATION & COUNTERS) ---
    @app.callback(
        Output('table-content', 'children'),
        Input('map', 'clickData'), 
        Input('map', 'selectedData'),
        Input({'type': 'histogram-slider', 'column': ALL}, 'value'), 
        State({'type': 'histogram-slider', 'column': ALL}, 'id'),
        Input({'type': 'categorical-dropdown', 'column': ALL}, 'value'), 
        State({'type': 'categorical-dropdown', 'column': ALL}, 'id'),
        Input('select-all-btn', 'n_clicks'), 
        Input('deselect-all-btn', 'n_clicks'),
        Input('table-layer-dropdown', 'value')
    )
    def update_table(click_data, selected_data, slider_vals, slider_ids, cat_vals, cat_ids, sel, desel, active_layer_id):
        if not active_layer_id or active_layer_id not in dm.layers:
            return html.Div("No Layer Selected", style={'color':'white'})
        
        target_df = dm.layers[active_layer_id].copy()
        total_rows = len(target_df) # Counter: Total
        
        layer_meta = next((l for l in dm.metadata if l['id'] == active_layer_id), None)
        is_primary = layer_meta.get('is_primary', False) if layer_meta else False

        filtered_df = target_df
        
        if is_primary:
            if slider_ids and slider_vals:
                for value, sid in zip(slider_vals, slider_ids):
                    col = sid['column']
                    if col in filtered_df.columns and value: 
                        filtered_df = filtered_df[(filtered_df[col]>=value[0]) & (filtered_df[col]<=value[1])]
            if cat_ids:
                for values, cid in zip(cat_vals, cat_ids):
                    col = cid['column']
                    if col in filtered_df.columns and values: 
                        filtered_df = filtered_df[filtered_df[col].isin(values)]
        
        filtered_rows = len(filtered_df) # Counter: Filtered

        ctx = callback_context
        trig = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        show, df_disp = False, pd.DataFrame()

        if trig == 'select-all-btn': 
            show, df_disp = True, filtered_df
        elif trig == 'deselect-all-btn': 
            show = False
        
        elif selected_data and 'points' in selected_data:
            uuids = []
            for p in selected_data['points']:
                if p.get('customdata') and p['customdata'][3] == active_layer_id:
                    uuids.append(p['customdata'][0])
            
            valid_uuids = [u for u in uuids if u in filtered_df.index]
            if valid_uuids:
                show = True
                df_disp = filtered_df.loc[valid_uuids]

        elif click_data and 'points' in click_data:
            p = click_data['points'][0]
            if p.get('customdata') and p['customdata'][3] == active_layer_id:
                uuid_clicked = p['customdata'][0]
                if uuid_clicked in filtered_df.index:
                    show = True
                    df_disp = filtered_df.loc[[uuid_clicked]]
        
        selected_count = len(df_disp) if show and not df_disp.empty else 0 # Counter: Selected

        # --- COUNTER BADGES HTML ---
        counters_html = html.Div([
            html.Span(f"Total: {total_rows}", style={'backgroundColor':'#555', 'padding':'2px 6px', 'borderRadius':'4px', 'marginRight':'10px', 'fontSize':'11px', 'color':'#bdc3c7'}),
            html.Span(f"Filtered: {filtered_rows}", style={'backgroundColor':'#583CA5', 'padding':'2px 6px', 'borderRadius':'4px', 'marginRight':'10px', 'fontSize':'11px', 'color':'white'}),
            html.Span(f"Selected: {selected_count}", style={'backgroundColor':'#FBB800', 'padding':'2px 6px', 'borderRadius':'4px', 'fontSize':'11px', 'color':'#333', 'fontWeight':'bold'}),
        ], style={'display':'flex', 'justifyContent':'flex-end', 'padding':'5px 15px', 'borderBottom':'1px solid #444'})

        if not show or df_disp.empty:
            return html.Div([
                counters_html,
                html.Div([
                    html.I(className="fas fa-hand-pointer", style={'fontSize':'40px','marginBottom':'20px'}), 
                    html.H3("No data selected", style={'marginBottom':'10px', 'color':'white', 'fontFamily': 'Barlow Condensed'}), 
                    html.P(f"Active Layer: {layer_meta['name']}", style={'fontSize':'12px', 'color':'#FBB800'}),
                    html.P("Select points on map to view table. Ctrl + Shift to multi-select. Lasso or Box selections on the top-right corner", style={'color':'#bbb'})
                ], style={'display':'flex','flexDirection':'column','alignItems':'center','justifyContent':'center','height':'100%','color':'#7f8c8d'})
            ], style={'display':'flex', 'flexDirection':'column', 'height':'100%'})
        else:
            df_disp = df_disp.copy()
            
            # --- SANITIZATION FIX ---
            for col in df_disp.select_dtypes(include=['object']).columns:
                try:
                    df_disp[col] = df_disp[col].astype(str).str.replace(r'[\r\n]+', ' ', regex=True)
                except: pass

            df_disp['orig_uuid'] = df_disp.index 

            view_cols = [c for c in df_disp.columns if c not in ['Notes', 'Score', 'orig_uuid', 'row_uuid']]
            
            possible_ids = [c for c in view_cols if c.lower() in ['id', 'fid', 'name']]
            if possible_ids:
                view_cols.remove(possible_ids[0])
                view_cols.insert(0, possible_ids[0])

            table_columns = [{'name': i, 'id': i, 'editable': False} for i in view_cols]

            if 'Notes' in df_disp.columns:
                table_columns.append({'name': 'Notes', 'id': 'Notes', 'editable': True, 'type': 'text'})
            if 'Score' in df_disp.columns:
                table_columns.append({'name': 'Score', 'id': 'Score', 'editable': True, 'type': 'numeric', 'format': FormatTemplate.Format(precision=0, scheme=Scheme.fixed)})
            
            return html.Div([
                counters_html,
                dash_table.DataTable(
                    id={'type': 'table-export', 'index': 0}, 
                    data=df_disp.to_dict('records'),
                    columns=table_columns,
                    merge_duplicate_headers=False,
                    editable=True,
                    page_size=50, 
                    page_action='native', 
                    fixed_rows={'headers': True}, 
                    row_selectable='multi', 
                    selected_rows=list(range(len(df_disp))), 
                    sort_action='native', 
                    filter_action='native', 
                    style_table={'height':'calc(100% - 30px)','minWidth':'100%'}, 
                    style_cell={'textAlign':'left','padding':'5px','whiteSpace':'normal','height':'auto','fontFamily':'Mulish, sans-serif','fontSize':'11px','backgroundColor':'#44546A','color':'#ecf0f1','border':'1px solid #555555','minWidth':'100px','width':'100px','maxWidth':'200px'}, 
                    style_header={'fontWeight':'bold','backgroundColor':'#583CA5','color':'white','fontSize':'12px','border':'1px solid #555555', 'fontFamily': 'Barlow Condensed', 'letterSpacing': '0.5px', 'textTransform': 'uppercase'}, 
                    style_filter={'backgroundColor':'#555555','color':'white', 'border': '1px solid #777'}, 
                    style_data_conditional=[{'if': {'state': 'selected'}, 'backgroundColor': 'rgba(251, 184, 0, 0.2)', 'border': '1px solid #FBB800'}], 
                    export_format='csv'
                ),
                html.Div(style={'height': '150px', 'width':'100%'})
            ], style={'height': '100%', 'overflowY': 'auto', 'width': '100%'})

    @app.callback(Output("left-pane-container", "style"), Output("collapse-btn", "style"), Output("map-container", "style"), Output("table-ui-wrapper", "style"), Input("collapse-btn", "n_clicks"), State("collapse-btn", "style"), State("map-container", "style"), State("table-ui-wrapper", "style"))
    def toggle_layout(n, btn_style, map_style, table_style):
        collapsed = (n % 2 == 1)
        
        # Base style for the container holding the pane
        base = {'position':'fixed','top':0,'left':'45px','height':'100vh','zIndex':20}
        
        new_left = '45px' if collapsed else 'calc(45px + 25vw)'
        
        pane_style = {**base, 'display': 'none'} if collapsed else base
        
        # Update styles
        btn_style.update({'left': new_left, 'children': '›' if collapsed else '‹'})
        map_style.update({'left': new_left})
        table_style.update({'left': new_left})
        
        return pane_style, btn_style, map_style, table_style

    @app.callback(Output("table-panel", "style"), Output("table-toggle-btn", "style"), Output("table-state-store", "data"), Input("table-toggle-btn", "n_clicks"), Input("close-table-btn", "n_clicks"), State("table-state-store", "data"), State("table-panel", "style"), State("table-toggle-btn", "style"))
    def toggle_table(btn, close, is_open, panel, btn_st):
        trig = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else None
        new = not is_open if trig == "table-toggle-btn" else False
        panel['height'] = '40vh' if new else '0vh'
        btn_st.update({'backgroundColor': '#FBB800' if new else '#44546A', 'color': '#333' if new else 'white', 'marginBottom': '10px' if new else '15px'})
        return panel, btn_st, new

    return app