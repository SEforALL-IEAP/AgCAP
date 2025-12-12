import os
import glob
import geopandas as gpd
import pandas as pd

def extract_coords(input_path):
    # Read the vector file (shapefile, geopackage, geojson)
    gdf = gpd.read_file(input_path)

    # Check and convert CRS to WGS84 (EPSG:4326)
    if gdf.crs is None:
        raise ValueError(f"Input file {input_path} has no CRS defined.")
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Extract coordinates: points directly, centroids for other geometry types
    def get_xy(geom):
        if geom.geom_type == 'Point':
            return geom.x, geom.y
        else:
            centroid = geom.centroid
            return centroid.x, centroid.y

    coords = gdf.geometry.apply(get_xy)

    # Convert Series of tuples to DataFrame with columns X_COORD and Y_COORD
    coords_df = pd.DataFrame(coords.tolist(), columns=['X_COORD', 'Y_COORD'])

    return coords_df

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Supported vector file extensions including GeoJSON
    vector_exts = ['*.shp', '*.gpkg', '*.geojson']

    files_found = []
    for ext in vector_exts:
        files_found.extend(glob.glob(os.path.join(script_dir, ext)))

    if not files_found:
        print("No supported vector files (.shp, .gpkg, or .geojson) found in the script directory.")
        return

    for input_file in files_found:
        print(f"Processing file: {os.path.basename(input_file)}")
        try:
            coords_df = extract_coords(input_file)
        except Exception as e:
            print(f"Error processing {os.path.basename(input_file)}: {e}")
            continue

        base_name, _ = os.path.splitext(os.path.basename(input_file))
        output_csv = os.path.join(script_dir, f"{base_name}_XY_only.csv")

        coords_df.to_csv(output_csv, index=False)
        print(f"Coordinates exported to {output_csv}")

if __name__ == "__main__":
    main()
