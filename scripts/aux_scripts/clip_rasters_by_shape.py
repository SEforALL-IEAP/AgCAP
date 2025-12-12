import os
import glob
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping
from tkinter import Tk, filedialog

def main():
    folder = os.path.dirname(os.path.abspath(__file__))

    root = Tk()
    root.withdraw()
    print("Please select the vector file (GeoPackage or Shapefile) representing the clipping contour.")
    vector_path = filedialog.askopenfilename(
        title="Select vector file (GeoPackage or Shapefile) representing the clipping contour",
        filetypes=[("Vector files", "*.gpkg *.shp")]
    )
    if not vector_path:
        print("No vector file selected. Exiting.")
        return

    vector = gpd.read_file(vector_path)

    if vector.crs.is_geographic:
        vector = vector.to_crs(epsg=3395)
    buffered = vector.buffer(50000)
    buffered_gdf = gpd.GeoDataFrame(geometry=buffered, crs=vector.crs)

    tif_files = glob.glob(os.path.join(folder, "*.tif")) + glob.glob(os.path.join(folder, "*.tiff"))
    if not tif_files:
        print("No GeoTIFF files found in folder.")
        return

    for tif_path in tif_files:
        print(f"Processing {os.path.basename(tif_path)}...")
        with rasterio.open(tif_path) as src:
            if buffered_gdf.crs != src.crs:
                buffered_proj = buffered_gdf.to_crs(src.crs)
            else:
                buffered_proj = buffered_gdf

            geoms = [mapping(geom) for geom in buffered_proj.geometry]

            # Use filled=False to get a masked array where pixels outside shapes are masked (not zeroed)
            out_image, out_transform = mask(
                src,
                geoms,
                crop=True,
                filled=False  # pixels outside shape are masked, not zeroed
            )

            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "nodata": src.nodata,
                # Add compression options for smaller file size
                "compress": "LZW",       # or "DEFLATE", "PACKBITS", "JPEG" (JPEG is lossy)
                "predictor": 2           # improves compression for LZW/DEFLATE with integer data
            })

            base, ext = os.path.splitext(tif_path)
            out_tif = f"{base}_clipped{ext}"

            with rasterio.open(out_tif, "w", **out_meta) as dest:
                dest.write(out_image)

        print(f"Saved clipped raster to {os.path.basename(out_tif)}")

if __name__ == "__main__":
    main()