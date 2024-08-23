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

    def _process_group(self, data: GeoDataFrame, shapefile_gdf):
        lines = {}

        def get_key(row):
            return row["lineId"], row["direction"]

        def get_line(row):
            if get_key(row) not in lines:
                lines[get_key(row)] = shapefile_gdf[
                    (shapefile_gdf["ligne"] == row["lineId"])
                    & (shapefile_gdf["variante"] != row["direction"])
                    ].iloc[0]["geometry"]

            return lines[get_key(row)]

        def get_distance_on_line(row):
            try:
                line_geometry = get_line(row)
                # Get the distance from the start of the line to the point
                return line_geometry.project(row["be_geometry"])
            except IndexError:
                return 0

        # Add distance column
        data["distance"] = [get_distance_on_line(row) for _, row in data.iterrows()]

        output_data = gpd.GeoDataFrame()

        for (line_id, direction), rows_with_timestamp in data.groupby(
                ["lineId", "direction"]
        ):
            output_data = pd.concat(
                [
                    output_data,
                    self.attribute_ids(
                        rows_with_timestamp,
                        line_id,
                    ),
                ]
            )

        output_data.drop(
            inplace=True,
            columns=[
                "be_geometry",
            ],
        )

        output = []

        for timestamp, rows in output_data.groupby("timestamp"):
            # Set the timestamp of rows to the timestamp of the group
            rows["timestamp"] = timestamp

            # noinspection PyTypeChecker
            output.append(
                (
                    rows,
                    int(timestamp),
                )
            )

        return output

    @staticmethod
    def attribute_ids(
            rows_with_timestamp: pd.DataFrame,
            line_id,
    ):

        # Drop all identical geometries and timestamps
        rows_with_timestamp.drop_duplicates(
            subset=["geometry", "timestamp"], inplace=True
        )
        # Print rows where distance is NaN
        algorithm = IdentifyVehicleAlgorithm(rows_with_timestamp, line_id)
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
                    features.append(feature)

                latest_datas_with_uuid_df = pd.concat(
                    [
                        latest_datas_with_uuid_df,
                        gpd.GeoDataFrame.from_features(features),
                    ]
                )

        return latest_datas_with_uuid_df, sources, shapefile_gdf
