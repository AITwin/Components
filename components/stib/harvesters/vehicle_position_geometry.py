import json
import uuid
from functools import partial
from typing import Tuple, Dict, Any

import geopandas as gpd
import pandas as pd
from shapely import LineString

from components.stib.utils.converter import convert_dataframe_column_stop_to_generic
from src.components import Harvester


class _SegmentCache:
    be_cache: Dict[str, Any] = {}
    cache: Dict[str, Any] = {}

    segments_gdf: gpd.GeoDataFrame = None
    segments_gdf_be_crs: gpd.GeoDataFrame = None
    init_count = 0

    def __init__(self, segments):
        _SegmentCache.init_count += 1
        self.segments = segments

        if _SegmentCache.init_count > 1e4:
            _SegmentCache.init_count = 0
            _SegmentCache.be_cache = {}
            _SegmentCache.segments_gdf = None
            _SegmentCache.segments_gdf_be_crs = None

        if _SegmentCache.segments_gdf is None:
            _SegmentCache.segments_gdf = gpd.GeoDataFrame.from_features(
                segments.data["features"], crs="epsg:4326"
            )
            _SegmentCache.segments_gdf_be_crs = _SegmentCache.segments_gdf.to_crs(
                epsg=31370
            ).copy()

    def get_segment_be(self, start, line_id, direction):
        key = f"{start}_{line_id}_{direction}"

        if key in _SegmentCache.be_cache:
            return _SegmentCache.be_cache[key]

        segment_be_filtered = self.segments_gdf_be_crs[
            (self.segments_gdf_be_crs["start"] == start)
            & (self.segments_gdf_be_crs["line_id"] == line_id)
            & (self.segments_gdf_be_crs["direction"] == direction)
        ]

        if len(segment_be_filtered) == 0:
            return None

        segment_be: LineString = segment_be_filtered.iloc[0]["geometry"]

        _SegmentCache.be_cache[key] = segment_be

        return segment_be

    def get_segment(self, start, line_id, direction):
        key = f"{start}_{line_id}_{direction}"

        if key in _SegmentCache.cache:
            return _SegmentCache.cache[key]

        segment_filtered = self.segments_gdf[
            (self.segments_gdf["start"] == start)
            & (self.segments_gdf["line_id"] == line_id)
            & (self.segments_gdf["direction"] == direction)
        ]

        if len(segment_filtered) == 0:
            return None

        segment: LineString = segment_filtered.iloc[0]["geometry"]

        _SegmentCache.cache[key] = segment

        return segment


class STIBVehiclePositionGeometryHarvester(Harvester):
    def run(self, source, stib_segments, stib_stops):
        # Load the data from the collection result
        dataframe = pd.json_normalize(source.data)

        if len(dataframe) == 0:
            return

        segments = _SegmentCache(stib_segments)

        stib_stops_gdf = gpd.GeoDataFrame.from_features(stib_stops.data["features"])

        cleaned_data = self.clean_realtime_data_with_merged_data(
            dataframe, stib_stops_gdf
        )

        if len(cleaned_data) == 0:
            return

        interpolator = partial(
            self.interpolate_position,
            segments=segments,
        )

        cleaned_data["position"] = cleaned_data.apply(interpolator, axis=1)

        # Solve index must be unique for the to_json() method to work
        cleaned_data.index = list(range(len(cleaned_data)))

        # Remove where position is null
        cleaned_data = cleaned_data[cleaned_data["position"].notnull()]

        # Remove uuid
        cleaned_data = cleaned_data.drop(columns=["uuid", "stop_lat", "stop_lon"])

        output_data = []

        line_to_color = {}

        # Extract color dict from segments
        for (line_id, color), _ in segments.segments_gdf.groupby(["line_id", "color"]):
            line_to_color[line_id] = color

        for index, row in cleaned_data.iterrows():
            output_data.append(
                {
                    "id": index,
                    "pointId": row["pointId"],
                    "lineId": row["line_id"],
                    "geometry": row["position"],
                    "direction": row["direction"],
                    "distanceFromPoint": row["distanceFromPoint"],
                    "color": line_to_color[row["line_id"]],
                }
            )

        if not output_data:
            return

        geo_dataframes = gpd.GeoDataFrame(output_data, geometry="geometry")

        return json.loads(geo_dataframes.to_json())

    @staticmethod
    def interpolate_position(row_to_interpolate, segments):
        segment_be: LineString = segments.get_segment_be(
            row_to_interpolate["pointId"],
            row_to_interpolate["line_id"],
            row_to_interpolate["direction"],
        )

        if segment_be is None:
            return None
        percentage = row_to_interpolate["distanceFromPoint"] / segment_be.length

        segment = segments.get_segment(
            row_to_interpolate["pointId"],
            row_to_interpolate["line_id"],
            row_to_interpolate["direction"],
        )

        point_on_segment = segment.interpolate(percentage, normalized=True)

        return point_on_segment

    def clean_realtime_data_with_merged_data(self, realtime_data, stib_stops):
        realtime_data = STIBVehiclePositionGeometryHarvester.prepare_realtime_dataframe(
            realtime_data
        )

        if len(realtime_data) == 0:
            return realtime_data

        (
            matched_data_with_point_and_direction,
            unmatched_data,
        ) = STIBVehiclePositionGeometryHarvester.merge_on_both_direction_and_point(
            stib_stops, realtime_data
        )

        if len(unmatched_data) > 0:
            # For these, we will try to match with point and line but without direction
            (
                matched_data_with_point,
                unmatched_data_2,
            ) = self.merge_on_point_and_line(stib_stops, unmatched_data)
        else:
            matched_data_with_point = unmatched_data

        columns_to_keep = [
            "uuid",
            "pointId",
            "line_id",
            "directionId",
            "distanceFromPoint",
            "confidence_score",
            "stop_name",
            "stop_sequence",
            "stop_lat",
            "stop_lon",
            "direction_id",
        ]

        to_merge = []

        if not matched_data_with_point_and_direction.empty:
            matched_data_with_point_and_direction = (
                matched_data_with_point_and_direction[columns_to_keep]
            )
            matched_data_with_point_and_direction["confidence_score"] = 5
            to_merge.append(matched_data_with_point_and_direction)

        if not matched_data_with_point.empty:
            matched_data_with_point = matched_data_with_point[columns_to_keep]
            matched_data_with_point["confidence_score"] = 4
            to_merge.append(matched_data_with_point)

        if to_merge:
            merged_data = pd.concat(
                to_merge,
            )

            # Rename direction_id to direction
            merged_data = merged_data.rename(columns={"direction_id": "direction"})

            # Replace V by 0 and T by 1
            merged_data["direction"] = merged_data["direction"].replace(
                {"V": 1, "F": 2}
            )

            return merged_data

        return pd.DataFrame()

    @staticmethod
    def reset_realtime_dataframe_columns(input_dataframe):
        if input_dataframe.empty:
            return input_dataframe
        input_dataframe = input_dataframe[
            [
                "uuid",
                "pointId",
                "line_id",
                "directionId",
                "distanceFromPoint",
                "confidence_score",
            ]
        ]

        return input_dataframe

    @staticmethod
    def merge_on_both_direction_and_point(
        merged, realtime_data
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        # Insert direction in realtime_data based on wether the directionId stop sequence matching in merged stop is 0
        realtime_data = realtime_data.merge(
            merged,
            left_on=["directionId", "line_id"],
            right_on=["stop_id", "route_short_name"],
            how="left",
        )

        # Drop duplicates, keep the highest stop_sequence
        realtime_data = realtime_data.sort_values(
            by=["uuid", "stop_sequence"]
        ).drop_duplicates(subset=["uuid"], keep="last")

        unmatched_destination_id = realtime_data[realtime_data["stop_id"].isna()].copy()
        unmatched_destination_id = unmatched_destination_id.dropna(axis=1, how="all")

        realtime_data = realtime_data[realtime_data["stop_id"].notna()].copy()

        realtime_data = realtime_data[
            [
                "uuid",
                "pointId",
                "line_id",
                "directionId",
                "distanceFromPoint",
                "confidence_score",
                "direction_id",
            ]
        ]

        realtime_data = realtime_data.merge(
            merged,
            left_on=["pointId", "line_id", "direction_id"],
            right_on=["stop_id", "route_short_name", "direction_id"],
            how="left",
        )

        unmatched_point_but_with_matched_direction = (
            STIBVehiclePositionGeometryHarvester.reset_realtime_dataframe_columns(
                realtime_data[realtime_data["stop_id"].isna()].copy()
            )
        )
        unmatched_point_but_with_matched_direction = (
            STIBVehiclePositionGeometryHarvester.reset_realtime_dataframe_columns(
                unmatched_point_but_with_matched_direction.dropna(axis=1, how="all")
            )
        )

        unmatched_with_direction_and_point = pd.concat(
            [unmatched_destination_id, unmatched_point_but_with_matched_direction]
        )

        realtime_data = realtime_data[realtime_data["stop_id"].notna()].copy()

        return (
            realtime_data,
            unmatched_with_direction_and_point,
        )

    @staticmethod
    def treat_stops(stib_stops):
        return stib_stops

    @staticmethod
    def merge_on_point_and_line(stops, data_to_match):
        """
        Merge the unmatched data with the merged data on the pointId and line_id
        columns. Only if there are no two stops with the same stop_id on the same
        line.
        """
        data_to_match = data_to_match.merge(
            stops,
            left_on=["pointId", "line_id"],
            right_on=["stop_id", "route_short_name"],
            how="left",
        )

        # Get uuid of duplicated rows
        duplicated_uuid = data_to_match[data_to_match.duplicated(subset=["uuid"])][
            "uuid"
        ].unique()

        matched_data = data_to_match[
            data_to_match["stop_id"].notna()
            & ~data_to_match["uuid"].isin(duplicated_uuid)
        ].copy()

        unmatched_data = data_to_match[
            data_to_match["stop_id"].isna()
            | data_to_match["uuid"].isin(duplicated_uuid)
        ].copy()

        return (
            matched_data,
            STIBVehiclePositionGeometryHarvester.reset_realtime_dataframe_columns(
                unmatched_data
            ),
        )

    @staticmethod
    def prepare_realtime_dataframe(realtime_data):
        """
        Preprocesses the raw realtime data to remove invalid data and add additional columns.

        @param realtime_data: The raw realtime data.
        @type realtime_data: pd.DataFrame

        @return: The preprocessed data.
        @rtype: pd.DataFrame
        """
        # Convert pointId and directionId to int
        realtime_data["pointId"] = convert_dataframe_column_stop_to_generic(
            realtime_data["pointId"]
        )

        realtime_data["directionId"] = convert_dataframe_column_stop_to_generic(
            realtime_data["directionId"]
        )

        # Insert uuid and confidence_score columns
        realtime_data["uuid"] = [uuid.uuid4() for _ in range(len(realtime_data))]
        realtime_data["confidence_score"] = 0

        realtime_data = realtime_data.query("pointId > 7200 or pointId < 7000")

        # Rename lineId to line_id
        realtime_data = realtime_data.rename(columns={"lineId": "line_id"})

        # Remove rows where line_id is null
        realtime_data = realtime_data.dropna(subset=["line_id"]).copy()

        # Convert line_id to string and remove ".0" and "T" from end of values
        realtime_data["line_id"] = (
            realtime_data["line_id"].astype(str).str.replace(".0|T", "", regex=True)
        )

        return realtime_data
