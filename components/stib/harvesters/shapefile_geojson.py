import io
import json
import tempfile
import zipfile

import geopandas as gpd

from src.components import Harvester


class STIBShapefileGeoJSONHarvester(Harvester):
    def run(self, source):
        with tempfile.TemporaryDirectory() as tmpdir:
            z = zipfile.ZipFile(io.BytesIO(source.data))
            z.extractall(tmpdir)

            shp_files = [f for f in z.namelist() if f.endswith(".shp")]
            lines_shp = next(
                f
                for f in shp_files
                if "LINES" in f.upper() or "LIGNES" in f.upper()
            )

            gdf = gpd.read_file(f"{tmpdir}/{lines_shp}")

            gdf = gdf.rename(columns={"LineCode": "ligne", "ColorHex": "color_hex"})
            gdf.columns = [c.lower() if c != "geometry" else c for c in gdf.columns]

            gdf = gdf.to_crs("EPSG:4326")

            return json.loads(gdf.to_json())
