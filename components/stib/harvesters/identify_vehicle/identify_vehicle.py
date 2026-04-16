import json

import geopandas as gpd
import pandas as pd
from geopandas import GeoDataFrame

from components.stib.harvesters.identify_vehicle.algorithm import IdentifyVehicleAlgorithm
from components.stib.utils.converter import convert_shapefile_line_to_stops_line
from src.components import Harvester

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class STIBVehicleIdentifyHarvester(Harvester):

    def run(self, sources, stib_vehicle_identify, stib_shapefile):
        DATAPOINT_PER_BATCH = 25

        latest_10_data_with_uuid_df, query, shapefile_gdf = self.retrieve_data(
            sources, stib_vehicle_identify, stib_shapefile
        )

        shapefile_gdf = self.prepare_shapefile(shapefile_gdf)

        latest_timestamp = 0

        min_timestamp = min([source.date.timestamp() for source in sources])

        for i in range(0, len(query), DATAPOINT_PER_BATCH):
            # Initialize the geo data frame
            data_df = gpd.GeoDataFrame()
            # Merge the latest 10 data with the current batch
            data_df = pd.concat([data_df, latest_10_data_with_uuid_df])
            if not data_df.empty:
                data_df.set_crs(epsg=4326, inplace=True)
            else:
                data_df = gpd.GeoDataFrame()
            # Load each to GeoDataFrame and concat
            for item in query[i: i + DATAPOINT_PER_BATCH]:
                timestamp = item.date.timestamp()
                latest_timestamp = max(timestamp, latest_timestamp)
                if len(item.data["features"]) > 0:
                    data = gpd.GeoDataFrame.from_features(
                        item.data["features"], crs="EPSG:4326"
                    )
                    data["timestamp"] = timestamp
                    data_df = pd.concat([data_df, data])

            if data_df.empty:
                yield None
                continue

            # If uuid is not present, add it
            if "uuid" not in data_df.columns:
                data_df["uuid"] = [None for _ in range(len(data_df))]

            # set general crs to 4326
            data_df.set_crs(epsg=4326, inplace=True)

            # Add the be_geometry column to keep the original geometry but
            # still be able to retrieve distance in meters.
            data_df["be_geometry"] = data_df["geometry"]
            data_df["geometry"] = data_df["geometry"].set_crs(epsg=4326)
            data_df["be_geometry"] = data_df["be_geometry"].to_crs(epsg=31370)

            result = self._process_group(data_df, shapefile_gdf)

            if result:
                # Keep latest data with uuid in memory for next batch.
                # This allows the uuid to be kept between batches.
                latest_10_data_with_uuid = [data for data, timestamp in result[-10:]]
                latest_10_data_with_uuid_df = pd.concat(
                    latest_10_data_with_uuid, ignore_index=True
                )
                # Convert to GeoDataFrame
                latest_10_data_with_uuid_df = gpd.GeoDataFrame(
                    latest_10_data_with_uuid_df, crs="EPSG:4326"
                )

            for data, data_timestamp in result:
                if data_timestamp < min_timestamp:
                    continue
                # Set uuid as only index
                data.set_index("uuid", inplace=True, drop=False)
                # Make a copy of the data to avoid modifying the original data
                data = data.copy()

                # Ensure id matches uuid
                data["id"] = data["uuid"]

                data_gdp = gpd.GeoDataFrame(data, crs="EPSG:4326")

                yield json.loads(data_gdp.to_json())

    @staticmethod
    def prepare_shapefile(shapefile_gdf):
        # TO belgium Lambert 72
        shapefile_gdf = shapefile_gdf.to_crs("EPSG:31370")

        shapefile_gdf["ligne"] = shapefile_gdf["ligne"].apply(
            convert_shapefile_line_to_stops_line
        )

        return shapefile_gdf

    @staticmethod
    def _process_group(data_df, shapefile_gdf):
        result = []

        for (line_id, direction), data_for_line_id in data_df.groupby(
            ["lineId", "direction"]
        ):
            shapefile_for_line = shapefile_gdf[
                (shapefile_gdf["ligne"] == str(line_id))
                & (shapefile_gdf["variante"] != direction)
            ]

            if len(shapefile_for_line) == 0:
                continue

            line_geometry = shapefile_for_line.iloc[0]["geometry"]

            data_for_line_id = data_for_line_id.copy()
            data_for_line_id["distance"] = data_for_line_id["be_geometry"].apply(
                lambda point: line_geometry.project(point)
            )

            algorithm = IdentifyVehicleAlgorithm(data_for_line_id, line_id)

            algorithm.match_iter()

            algorithm_result = algorithm.get_result()

            if algorithm_result is None or algorithm_result.empty:
                continue

            for timestamp, data in algorithm_result.groupby("timestamp"):
                data = gpd.GeoDataFrame(data, crs="EPSG:4326")

                result.append((data, timestamp))

        return result

    @staticmethod
    def _process_line(
        line_id, direction, data_for_line_id, shapefile_gdf
    ):
        shapefile_for_line = shapefile_gdf[shapefile_gdf["ligne"] == str(line_id)]

        if len(shapefile_for_line) == 0:
            return None

        total_line_distance = shapefile_for_line.iloc[0]["geometry"].length

        algorithm = IdentifyVehicleAlgorithm(data_for_line_id, line_id)

        algorithm.match_iter()

        return algorithm.get_result()

    def retrieve_data(self, sources, stib_vehicle_identify, stib_shapefile):
        shapefile_gdf = gpd.GeoDataFrame.from_features(
            stib_shapefile.data["features"], crs="EPSG:4326"
        )

        latest_datas_with_uuid_df = gpd.GeoDataFrame()

        if stib_vehicle_identify:
            for latest_data_with_uuid in stib_vehicle_identify:
                features = []

                for feature in latest_data_with_uuid.data["features"]:
                    feature["properties"]["uuid"] = feature["id"]
                    feature["properties"].pop("id", None)
                    features.append(feature)

                latest_datas_with_uuid_df = pd.concat(
                    [
                        latest_datas_with_uuid_df,
                        gpd.GeoDataFrame.from_features(features),
                    ]
                )

        return latest_datas_with_uuid_df, sources, shapefile_gdf
