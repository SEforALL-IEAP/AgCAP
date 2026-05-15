import inspect
import socket
import warnings
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

# --- Data Science & Numeric Imports ---
import numpy as np
import pandas as pd
import scipy.spatial
from scipy.spatial import Voronoi

# --- Geospatial Imports (Vector) ---
import geopandas as gpd  # Imported once, globally
import pyproj
import shapely
import shapely.ops
from shapely.geometry import Point, mapping

# --- Geospatial Imports (Raster) ---
import rasterio
import rasterio.mask
from rasterio.windows import from_bounds
from rasterstats import gen_zonal_stats
from rasterstats import zonal_stats

# --- Visualization & Interactive Imports ---
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- Global Configurations ---
warnings.filterwarnings('ignore')

# Initialize hidden Tkinter root for file dialogs (only happens once now)
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)


# --- FUNCTIONS ---

def spatial_join_largest_overlap(settlements_gdf, area_gdf, area_value_column, new_column_name=None):
    """
    Spatial join where each polygon in settlements_gdf is assigned the attribute value from area_gdf,
    based on the polygon in area_gdf with which it has the largest overlap.
    Preserves the original index of settlements_gdf.
    """
    sjoin_sig = inspect.signature(gpd.sjoin)
    join_kwargs = {'predicate': 'intersects'} if 'predicate' in sjoin_sig.parameters else {'op': 'intersects'}
    
    if new_column_name is None:
        new_column_name = area_value_column
    if settlements_gdf.crs != area_gdf.crs:
        area_gdf = area_gdf.to_crs(settlements_gdf.crs)
        
    settlements_gdf_indexed = settlements_gdf.copy()
    settlements_gdf_indexed['_original_index'] = settlements_gdf_indexed.index
    settlements_sub = settlements_gdf_indexed[['_original_index', 'geometry']]
    area_sub = area_gdf[[area_value_column, 'geometry']].copy()
    
    joined = gpd.sjoin(settlements_sub, area_sub, how='left', **join_kwargs)
    
    if joined.empty:
        settlements_gdf[new_column_name] = pd.NA
        return settlements_gdf

    def intersection_area(row):
        if pd.isna(row.index_right):
            return 0
        area_geom = area_sub.loc[row.index_right].geometry
        return row.geometry.intersection(area_geom).area

    joined['intersection_area'] = joined.apply(intersection_area, axis=1)
    sorted_joined = joined.sort_values(by=['_original_index', 'intersection_area'], ascending=[True, False])
    largest_overlaps_selected = sorted_joined.drop_duplicates(subset=['_original_index'], keep='first')
    map_series = largest_overlaps_selected.set_index('_original_index')[area_value_column]
    settlements_gdf[new_column_name] = settlements_gdf.index.map(map_series)
    
    return settlements_gdf

def get_admin_name(clusters, admin, admin_col_name):
    clusters_support = clusters[['id', 'geometry']].to_crs('EPSG:4326')
    clusters_support_centroid = clusters_support.copy()
    clusters_support_centroid.geometry = clusters_support_centroid.centroid
    
    # Updated to use predicate instead of op (future-proofing)
    clusters_support_centroid_2 = gpd.sjoin(
        clusters_support_centroid, 
        admin[['geometry', admin_col_name]], 
        predicate='intersects'
    ).drop(['index_right'], axis=1)
    
    group_by_id = clusters_support_centroid_2.groupby('id')[[admin_col_name]].first().reset_index()
    clusters = pd.merge(clusters, group_by_id[['id', admin_col_name]], on='id', how='left')
    
    print(datetime.now())
    return clusters

def run_zonal_stats_clipped(polygons_gdf, raster_path, stats=['mean'], col_prefix=None, fill_na=None):
    """
    Calculates zonal statistics against a large raster by pre-clipping the raster data 
    into a small NumPy array, preventing MemoryErrors.
    """
    output_gdf = polygons_gdf.copy()
    if isinstance(stats, str):
        stats = [stats]
        
    with rasterio.open(raster_path) as src:
        raster_crs = src.crs
        raster_nodata = src.nodata
        
        if polygons_gdf.crs != raster_crs:
            working_gdf = polygons_gdf.to_crs(raster_crs)
        else:
            working_gdf = polygons_gdf.copy()
            
        clip_bounds = working_gdf.total_bounds
        left, bottom, right, top = clip_bounds
        print('Calculating raster window and reading only relevant data...')
        window = from_bounds(*clip_bounds, transform=src.transform)
        data = src.read(1, window=window)
        new_affine = src.window_transform(window)
        print(f'Data array shape read: {data.shape}')
        
    print('Running zonal statistics on the clipped array...')
    stats_generator = gen_zonal_stats(working_gdf, data, affine=new_affine, stats=stats, all_touched=True, nodata=raster_nodata)
    results = list(stats_generator)
    
    for stat in stats:
        new_col_name = col_prefix if len(stats) == 1 and col_prefix else f'{col_prefix}_{stat}'
        default_value = fill_na if fill_na is not None else np.nan
        values = [res.get(stat, default_value) for res in results]
        output_gdf[new_col_name] = values
        if fill_na is not None:
            output_gdf[new_col_name] = output_gdf[new_col_name].fillna(fill_na)
        output_gdf[new_col_name] = output_gdf[new_col_name].astype(float).round(1)
        
    return output_gdf

def calc_Crop_sqkm(df, col_list):
    """ 
    Estimates the area per cropland type in each location by multiplying with the total area each row represents.
    """
    df['Crop_pix_sum'] = df[col_list].sum(axis=1)
    for col in col_list:
        df[col] = df[col] / df['Crop_pix_sum'] * df['Vor_area_ha']
    df = df.drop('Crop_pix_sum', axis=1)
    return df

def distance_from_lines(name, admin_gdf, project_crs, settlements_gdf, lines_path):
    """
    Calculates the distance from settlements to the nearest point on a line network.
    """
    start_time = datetime.now()
    print(f'--- Starting analysis for {name} at {start_time} ---')
    print(f'Preparing settlements...')
    
    clusters = settlements_gdf.copy()
    if clusters.crs != project_crs:
        clusters = clusters.to_crs(project_crs)
        
    if clusters.geom_type.iloc[0] == 'Polygon' or clusters.geom_type.iloc[0] == 'MultiPolygon':
        clusters['centroid_geom'] = clusters.geometry.centroid
    else:
        clusters['centroid_geom'] = clusters.geometry
        
    print(f'Reading and processing lines...')
    try:
        lines = gpd.read_file(lines_path)
    except Exception as e:
        print(f'Error reading lines file: {e}')
        return None
        
    if lines.crs != admin_gdf.crs:
        lines = lines.to_crs(admin_gdf.crs)
        
    lines_clip = gpd.clip(lines, admin_gdf)
    lines_clip = lines_clip.to_crs(project_crs)
    
    if lines_clip.empty:
        print(f'Warning: No {name} lines found within the admin boundary.')
        clusters[f'{name}Dist'] = np.nan
        return clusters
        
    print(f'Discretizing lines into points (100m intervals)...')
    line_coords = []
    for geom in lines_clip.geometry:
        if geom is not None and (not geom.is_empty):
            length = geom.length
            distances = np.arange(0, length, 100)
            points = [geom.interpolate(d) for d in distances]
            line_coords.extend([(p.x, p.y) for p in points])
            
    if not line_coords:
        print('Lines exist but were too short to generate points.')
        clusters[f'{name}Dist'] = np.nan
        return clusters
        
    s1_arr = np.array(line_coords)
    print(f'Running KDTree algorithm...')
    s2_arr = np.column_stack((clusters['centroid_geom'].x, clusters['centroid_geom'].y))
    
    mytree = scipy.spatial.cKDTree(s1_arr)
    dist, indexes = mytree.query(s2_arr, k=1)
    clusters[f'{name}Dist'] = dist / 1000
    
    print('Checking for exact physical overlaps...')
    centroids_gdf = gpd.GeoDataFrame(clusters[['id']], geometry=clusters['centroid_geom'], crs=project_crs)
    lines_geo = lines_clip[['geometry']]
    join_result = gpd.sjoin(centroids_gdf, lines_geo, predicate='intersects', how='inner')
    touching_ids = join_result['id'].unique()
    clusters.loc[clusters['id'].isin(touching_ids), f'{name}Dist'] = 0
    
    if 'centroid_geom' in clusters.columns:
        del clusters['centroid_geom']
        
    end_time = datetime.now()
    print(f'--- Finished {name}. Duration: {end_time - start_time} ---')
    return clusters

def distance_from_points(name, admin_gdf, project_crs, settlements_gdf, points_path):
    """
    Calculates the distance from settlements to the nearest destination point.
    """
    start_time = datetime.now()
    print(f'--- Starting Point Analysis for {name} at {start_time} ---')
    
    clusters = settlements_gdf.copy()
    if clusters.crs != project_crs:
        clusters = clusters.to_crs(project_crs)
        
    if clusters.geom_type.iloc[0] == 'Polygon' or clusters.geom_type.iloc[0] == 'MultiPolygon':
        clusters['centroid_geom'] = clusters.geometry.centroid
    else:
        clusters['centroid_geom'] = clusters.geometry
        
    print(f'Reading destination points...')
    try:
        dest_points = gpd.read_file(points_path)
    except Exception as e:
        print(f'Error reading points file: {e}')
        return None
        
    if dest_points.crs != admin_gdf.crs:
        dest_points = dest_points.to_crs(admin_gdf.crs)
        
    dest_points_clip = gpd.clip(dest_points, admin_gdf)
    dest_points_clip = dest_points_clip.to_crs(project_crs)
    
    if dest_points_clip.empty:
        print(f'Warning: No {name} points found within the admin boundary.')
        clusters[f'{name}Dist'] = np.nan
        if 'centroid_geom' in clusters.columns:
            del clusters['centroid_geom']
        return clusters
        
    print(f'Running KDTree algorithm...')
    s1_arr = np.column_stack((dest_points_clip.geometry.x, dest_points_clip.geometry.y))
    s2_arr = np.column_stack((clusters['centroid_geom'].x, clusters['centroid_geom'].y))
    
    mytree = scipy.spatial.cKDTree(s1_arr)
    dist, indexes = mytree.query(s2_arr, k=1)
    clusters[f'{name}Dist'] = dist / 1000
    
    if 'centroid_geom' in clusters.columns:
        del clusters['centroid_geom']
        
    end_time = datetime.now()
    print(f'--- Finished {name}. Duration: {end_time - start_time} ---')
    return clusters

def calculate_raster_overlap_area_ha(raster_path, geodf, raster_crs, projected_crs, value_to_check=3, area_col='overlap_area_ha'):
    """
    Calculates the overlap area (in hectares) of raster pixels with a specific value inside polygons.
    """
    gdf = geodf.copy()
    with rasterio.open(raster_path) as src:
        pixel_width = src.transform.a
        pixel_height = -src.transform.e
        overlap_areas = []
        transformer = pyproj.Transformer.from_crs(raster_crs, projected_crs, always_xy=True)
        
        for geom in gdf.geometry:
            g_proj = gpd.GeoSeries([geom], crs=geodf.crs).to_crs(projected_crs).iloc[0]
            lon_min = geom.bounds[0]
            lat_max = geom.bounds[3]
            lon_max = lon_min + pixel_width
            lat_min = lat_max - pixel_height
            
            x1, y1 = transformer.transform(lon_min, lat_max)
            x2, y2 = transformer.transform(lon_max, lat_min)
            pixel_size_x = abs(x2 - x1)
            pixel_size_y = abs(y2 - y1)
            pixel_area_m2 = pixel_size_x * pixel_size_y
            
            try:
                out_image, out_transform = rasterio.mask.mask(src, [mapping(geom)], crop=True, filled=False)
            except Exception:
                overlap_areas.append(0.0)
                continue
                
            masked_data = out_image[0]
            count_pixels = np.sum(masked_data == value_to_check)
            area_ha = count_pixels * pixel_area_m2 / 10000
            overlap_areas.append(area_ha)
            
    gdf[area_col] = overlap_areas
    return gdf

def createVoronoi_3(admin, settlements, crs_projected, crs, boundary_point_spacing=200, simplify_settlements=True):
    """
    Create Voronoi polygons around settlement polygons clipped by admin boundaries.
    """
    admin_gdf_prj = admin.to_crs(crs_projected)
    print(f'Simplifying admin boundary with tolerance={boundary_point_spacing} meters...')
    admin_gdf_prj['geometry'] = admin_gdf_prj['geometry'].simplify(tolerance=boundary_point_spacing, preserve_topology=True)
    print('Admin boundary simplified.')
    
    admin_geom = admin_gdf_prj.geometry.iloc[0]
    bound = admin_geom.buffer(50000).envelope.boundary
    num_points = int(np.ceil(bound.length / boundary_point_spacing)) + 1
    boundarypoints = [bound.interpolate(distance=d) for d in np.linspace(0, bound.length, num_points)]
    boundarycoords = np.array([[p.x, p.y] for p in boundarypoints])
    print(f'Boundary area defined with {num_points} boundary points spaced {boundary_point_spacing} meters apart.')
    
    settles_gdf_prj = settlements.to_crs(crs_projected)
    if simplify_settlements:
        print(f'Simplifying settlement geometries with tolerance={boundary_point_spacing} meters...')
        settles_gdf_prj['geometry'] = settles_gdf_prj['geometry'].simplify(tolerance=boundary_point_spacing, preserve_topology=True)
        print('Settlement geometries simplified.')
    else:
        print('Skipping settlement simplification.')
        
    points_list = []
    total_vertices = 0
    for idx, row in settles_gdf_prj.iterrows():
        polygon_uid = row['id']
        geometry = row.geometry
        polygons = [geometry] if geometry.geom_type == 'Polygon' else geometry.geoms
        for polygon in polygons:
            exterior_coords = np.array(polygon.exterior.coords)
            total_vertices += len(exterior_coords)
            for coord in exterior_coords:
                points_list.append({'id': idx, 'uid': polygon_uid, 'geometry': Point(coord)})
            if total_vertices % 100 == 0:
                pass
                #print(f'Processed {total_vertices} perimeter vertices so far...')
                
    print(f'Total perimeter vertices extracted from settlements: {total_vertices}')
    points_df = gpd.GeoDataFrame(points_list, crs=crs_projected)
    
    print('Perimeter vertices generated, starting Voronoi polygon creation...')
    x = points_df.geometry.x.values
    y = points_df.geometry.y.values
    coords = np.vstack((x, y)).T
    all_coords = np.vstack((boundarycoords, coords))
    print(f'Total points for Voronoi diagram (boundary + polygon vertices): {all_coords.shape[0]}')
    
    vor = Voronoi(all_coords)
    print('Voronoi diagram vertices and ridges computed, constructing polygons...')
    
    lines = []
    for i, line_indices in enumerate(vor.ridge_vertices):
        if -1 not in line_indices:
            lines.append(shapely.geometry.LineString(vor.vertices[line_indices]))
        if i % 100 == 0 and i > 0:
            pass
            #print(f'Processed {i} Voronoi ridges out of {len(vor.ridge_vertices)}')
            
    polys = shapely.ops.polygonize(lines)
    voronois = gpd.GeoDataFrame(geometry=gpd.GeoSeries(polys), crs=crs_projected)
    print('Voronoi polygons constructed.')
    
    voronois['geometry'] = voronois['geometry'].buffer(0)
    print('Fixed Voronoi polygon geometries with buffer(0).')
    
    result = gpd.clip(voronois, admin_geom)
    result['uniqueID'] = range(1, len(result) + 1)
    print('Voronoi polygons clipped to admin boundary.')
    
    buffered_result = result.copy()
    buffered_result['geometry'] = buffered_result.geometry.buffer(15)
    
    if points_df.sindex is None:
        points_df.sindex
    if buffered_result.sindex is None:
        buffered_result.sindex
        
    buffered_result_withID = gpd.sjoin(buffered_result, points_df[['geometry', 'uid']], how='left').drop(columns=['index_right'])
    result = result.merge(buffered_result_withID[['uniqueID', 'uid']], on='uniqueID', how='left')
    result_dissolved = result.dissolve(by='uid')
    print('Dissolved Voronoi polygons completed..')
    
    result_dissolved['Vor_area_sq.km'] = result_dissolved.geometry.area / 10 ** 6
    result_dissolved['Vor_area_ha'] = result_dissolved['Vor_area_sq.km'] * 100
    result_dissolved = result_dissolved.to_crs(crs)
    print('Voronoi area calculation and CRS re-projection completed.')
    
    return result_dissolved

def normalize_series(series):
    min_val = series.min()
    max_val = series.max()
    series_norm = (series - min_val) / (max_val - min_val)
    return series_norm

#Adds a min-max normalized column to a GeoDataFrame and returns the updated GeoDataFrame.
def normalize_index_column(gdf, col_name, copy=False):
    """
    Adds a min-max normalized column to a GeoDataFrame.

    Parameters:
        gdf (GeoDataFrame): Input GeoDataFrame.
        col_name (str): Column to normalize.
        copy (bool, optional): If True, return a new GeoDataFrame with normalized column.
                               If False (default), add normalized column to the original GeoDataFrame in place.

    Returns:
        GeoDataFrame: GeoDataFrame with the normalized column added.
    """
    min_val = gdf[col_name].min()
    max_val = gdf[col_name].max()

    if copy:
        new_gdf = gdf.copy()
        new_gdf[f"{col_name}_norm"] = (new_gdf[col_name] - min_val) / (max_val - min_val)
        return new_gdf
    else:
        gdf[f"{col_name}_norm"] = (gdf[col_name] - min_val) / (max_val - min_val)
        return gdf

def create_FAI(gdf, crop_ext_col, crop_int_col, crop_ext_w=0.5, crop_int_w=0.5):
    """
    Create a Farming Activity Index (FAI).
    """
    if not (0 <= crop_ext_w <= 1 and 0 <= crop_int_w <= 1):
        raise ValueError('Weights must be between 0 and 1.')
    if abs(crop_ext_w + crop_int_w - 1) > 1e-09:
        raise ValueError('The sum of weights must be exactly 1.')
        
    result = gdf
    normalize_index_column(result, crop_ext_col, copy=False)
    ext_norm_col = f'{crop_ext_col}_norm'
    normalize_index_column(result, crop_int_col, copy=False)
    int_norm_col = f'{crop_int_col}_norm'
    
    result['FAI'] = result[ext_norm_col] * crop_ext_w + result[int_norm_col] * crop_int_w
    normalize_index_column(result, 'FAI', copy=False)
    result['FAI_norm'] = result['FAI_norm'].round(3)
    result['FAI'] = result['FAI'].round(3)
    result = result.drop(columns=[ext_norm_col, int_norm_col])
    return result

def Create_MAI(gdf, airport_dist_col, port_dist_col, railway_dist_col, capital_dist_col, cities_dist_col, pop_20km_col, airport_dist_w, port_dist_w, railway_dist_w, capital_dist_w, cities_dist_w, pop_20km_w):
    """
    Creates a normalized Market Accessibility Index (MAI).
    """
    required_columns = [airport_dist_col, port_dist_col, railway_dist_col, capital_dist_col, cities_dist_col, pop_20km_col]
    missing_cols = [col for col in required_columns if col not in gdf.columns]
    
    if missing_cols:
        raise ValueError(f'The following required columns are missing from the GeoDataFrame: {missing_cols}')
        
    total_weight = airport_dist_w + port_dist_w + railway_dist_w + capital_dist_w + cities_dist_w + pop_20km_w
    if not abs(total_weight - 1.0) < 1e-08:
        raise ValueError(f'The sum of weights must be 1.0, but it is {total_weight}')
        
    travel_cols = [airport_dist_col, port_dist_col, railway_dist_col, capital_dist_col, cities_dist_col]
    norm_travel_cols = []
    
    for col in travel_cols:
        norm_col = f'{col}_norm'
        gdf[norm_col] = normalize_series(gdf[col])
        norm_travel_cols.append(norm_col)
        
    for norm_col in norm_travel_cols:
        gdf[f'{norm_col}_acc'] = 1 - gdf[norm_col]
        
    pop_norm_col = f'{pop_20km_col}_norm'
    gdf[pop_norm_col] = normalize_series(gdf[pop_20km_col])
    
    weighted_avg = (gdf[f'{airport_dist_col}_norm_acc'] * airport_dist_w + 
                    gdf[f'{port_dist_col}_norm_acc'] * port_dist_w + 
                    gdf[f'{railway_dist_col}_norm_acc'] * railway_dist_w + 
                    gdf[f'{capital_dist_col}_norm_acc'] * capital_dist_w + 
                    gdf[f'{cities_dist_col}_norm_acc'] * cities_dist_w + 
                    gdf[pop_norm_col] * pop_20km_w) / total_weight
                    
    MAI_norm = normalize_series(weighted_avg).round(3)
    cols_to_drop = norm_travel_cols + [f'{col}_acc' for col in norm_travel_cols] + [pop_norm_col]
    gdf.drop(columns=cols_to_drop, inplace=True)
    return MAI_norm

def composite_index(series_list, weights, normalize_output=True):
    """
    Build a composite index by weighted average of input series.
    """
    if len(series_list) != len(weights):
        raise ValueError('Length of series_list and weights must be the same.')
    if not all((0 <= w <= 1 for w in weights)):
        raise ValueError('All weights must be between 0 and 1.')
    if not abs(sum(weights) - 1) < 1e-08:
        raise ValueError('Weights must sum to 1.')
        
    normalized_series = []
    for s in series_list:
        min_val = s.min()
        max_val = s.max()
        if max_val == min_val:
            norm_s = s - min_val
        else:
            norm_s = (s - min_val) / (max_val - min_val)
        normalized_series.append(norm_s)
        
    weighted_sum = sum((w * s for w, s in zip(weights, normalized_series)))
    
    if normalize_output:
        min_val = weighted_sum.min()
        max_val = weighted_sum.max()
        if max_val == min_val:
            composite_index = weighted_sum - min_val
        else:
            composite_index = (weighted_sum - min_val) / (max_val - min_val)
    else:
        composite_index = weighted_sum
        
    return composite_index

def plot_histogram_map(settles_gdf, default_column, figure_title='', point_size=2.5, point_opacity=0.5):
    centroids_gdf = settles_gdf.copy()
    centroids_gdf.geometry = centroids_gdf.geometry.centroid
    centroids_gdf = centroids_gdf[centroids_gdf[default_column] > 0]
    filtered_settles_gdf = settles_gdf[settles_gdf[default_column] > 0]
    
    fig = make_subplots(
        rows=1, cols=2, 
        subplot_titles=('Histogram', 'Map'), 
        specs=[[{'type': 'histogram'}, {'type': 'scattermapbox'}]], 
        horizontal_spacing=0.02
    )
    
    fig.add_trace(go.Histogram(
        x=filtered_settles_gdf[default_column], 
        marker_color='skyblue', 
        marker_line_color='black', 
        marker_line_width=1, 
        opacity=1, 
        name=default_column
    ), row=1, col=1)
    
    fig.add_trace(go.Scattermapbox(
        lat=centroids_gdf.geometry.y, 
        lon=centroids_gdf.geometry.x, 
        mode='markers', 
        marker=go.scattermapbox.Marker(
            size=point_size, 
            color=centroids_gdf[default_column], 
            colorscale='bluered_r', 
            colorbar=dict(title=default_column, orientation='h', y=-0.05, x=0.5, xanchor='center', yanchor='top', len=0.8, thickness=10), 
            cmin=centroids_gdf[default_column].min(), 
            cmax=centroids_gdf[default_column].max(), 
            opacity=point_opacity
        ), 
        hovertemplate=f'<b>{default_column}</b>: %{{marker.color:.3f}}<br>Lat: %{{lat:.3f}}<br>Lon: %{{lon:.3f}}<extra></extra>', 
        hoverinfo='text', 
        name='points'
    ), row=1, col=2)
    
    fig.update_yaxes(title_text='Frequency', row=1, col=1)
    fig.update_layout(
        height=600, 
        showlegend=False, 
        title_text=figure_title, 
        mapbox=dict(
            style='open-street-map', 
            center=dict(lat=centroids_gdf.geometry.y.mean(), lon=centroids_gdf.geometry.x.mean()), 
            zoom=4
        ), 
        hovermode='closest'
    )
    fig.show(config={'scrollZoom': True})
    return fig

def find_available_port(default_port=8050):
    port = default_port
    while port < 65535:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
            return port
        except OSError:
            port += 1
    raise RuntimeError('Could not find an available port.')

def get_single_input_file_path(input_directory_path: Union[str, Path], allowed_extensions: Optional[List[str]]=None) -> Path:
    """
    Checks the specified directory for exactly one file matching the allowed extensions 
    and returns its path.
    """
    input_dir = Path(input_directory_path)
    if not input_dir.is_dir():
        raise FileNotFoundError(f'Input directory not found or is not a directory: {input_dir}')
        
    if allowed_extensions:
        normalized_extensions = [ext if ext.startswith('.') else f'.{ext}' for ext in [e.lower() for e in allowed_extensions]]
        
    matching_file_list = []
    for p in input_dir.iterdir():
        if p.is_file():
            if allowed_extensions:
                if p.suffix.lower() in normalized_extensions:
                    matching_file_list.append(p)
            else:
                matching_file_list.append(p)
                
    num_files = len(matching_file_list)
    if num_files == 0:
        ext_hint = f' matching extensions {allowed_extensions}' if allowed_extensions else ''
        raise FileNotFoundError(f'No files{ext_hint} found in the input folder: {input_dir}. Please ensure the required file is placed there.')
    elif num_files > 1:
        file_names = '\n- ' + '\n- '.join([f.name for f in matching_file_list])
        raise ValueError(f'Multiple files ({num_files}) matching the specified criteria found in: {input_dir}.\nPlease ensure **only one** file (e.g., one .shp or one .gpkg) is present for processing.Found files:{file_names}')
    else:
        return matching_file_list[0]

def get_multiple_input_file_path(input_directory_path: Union[str, Path], allowed_extensions: Optional[List[str]] = None) -> Path:
    """
    Checks the specified directory for files matching the allowed extensions.
    - If exactly one file is found, returns it.
    - If multiple files are found, prompts the user to select one.
    - If none are found, raises FileNotFoundError.
    """
    input_dir = Path(input_directory_path)
    if not input_dir.is_dir():
        raise FileNotFoundError(f'Input directory not found or is not a directory: {input_dir}')
        
    if allowed_extensions:
        normalized_extensions = [
            ext if ext.startswith('.') else f'.{ext}'
            for ext in [e.lower() for e in allowed_extensions]
        ]
        
    matching_file_list = []
    for p in input_dir.iterdir():
        if p.is_file():
            if allowed_extensions:
                if p.suffix.lower() in normalized_extensions:
                    matching_file_list.append(p)
            else:
                matching_file_list.append(p)
                
    num_files = len(matching_file_list)

    # No files found
    if num_files == 0:
        ext_hint = f' matching extensions {allowed_extensions}' if allowed_extensions else ''
        raise FileNotFoundError(
            f'No files{ext_hint} found in the input folder: {input_dir}. '
            'Please ensure the required file is placed there.'
        )

    # Exactly one file found → return it directly
    if num_files == 1:
        return matching_file_list[0]

    # Multiple files found → ASK USER
    print(f"\nMultiple files ({num_files}) found in: {input_dir}")
    print("Please select the file to use:\n")

    for i, f in enumerate(matching_file_list, start=1):
        print(f"  {i}. {f.name}")

    while True:
        selection = input("\nEnter the number of the file you want to use: ")
        try:
            idx = int(selection)
            if 1 <= idx <= num_files:
                return matching_file_list[idx - 1]
            else:
                print(f"Please enter a number between 1 and {num_files}.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def process_categorical_raster(gdf, raster_input, prefix):
    """
    Calculates categorical statistics for a raster and appends them to the 
    GeoDataFrame without writing to disk or duplicating geometries in memory.
    
    Args:
        gdf (geopandas.GeoDataFrame): The vector layer containing clusters.
        raster_input (str or rasterio.DatasetReader): Path to raster or open rasterio object.
        prefix (str): Prefix for the new columns.
        
    Returns:
        geopandas.GeoDataFrame: The original GDF with new columns attached.
    """
    print(f"Starting {prefix} extraction at {datetime.now()}")

    # 1. Calculate Stats Only
    # We set geojson_out=False. This is critical for memory. 
    # It returns a list of dicts: [{'1': 20, '2': 5}, ...] rather than 
    # heavy FeatureCollection objects.
    stats = zonal_stats(
        gdf,
        raster_input,
        categorical=True,
        prefix=prefix,
        geojson_out=False, 
        all_touched=True,
        #nodata=-128 # Optional: define if you know your nodata value
    )

    # 2. Convert to DataFrame
    # This creates a lightweight table of just the new data
    stats_df = pd.DataFrame(stats)

    # 3. Handle Missing Values (Optional but recommended for categorical data)
    # If a polygon doesn't overlap with category '5', it usually comes back as NaN.
    # We fill with 0 to keep data clean, but you can remove this if you prefer NaNs.
    stats_df = stats_df.fillna(0)

    # 4. Merge efficiently
    # We ensure the index matches the original GDF to perform a horizontal concatenation
    # This avoids spatial joins or ID lookups, which are computationally expensive.
    stats_df.index = gdf.index
    
    # Concatenate along columns (axis=1)
    # result_gdf = pd.concat([gdf, stats_df], axis=1) 
    
    # ALTERNATIVE: If you want to modify 'vor_poly' in place to save even more memory:
    for col in stats_df.columns:
        gdf[col] = stats_df[col]

    print(f"{prefix} processing completed at {datetime.now()}")
    
    return gdf