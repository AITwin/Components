import json

import geopandas as gpd
import pandas as pd
import pyproj
import shapely
from shapely import (
    LineString,
    Point,
)
from shapely.ops import transform

from components.stib.utils.converter import convert_shapefile_line_to_stops_line
from src.components import Harvester

project = pyproj.Transformer.from_proj(
    pyproj.Proj("epsg:4326"),  # source coordinate system
    pyproj.Proj("epsg:31370"),
)  # destination coordinate system


class STIBSegmentsHarvester(Harvester):

    def run(self, source, stib_stops):
        shapefile = gpd.GeoDataFrame.from_features(source.data["features"])
        shapefile["ligne"] = shapefile["ligne"].apply(
            convert_shapefile_line_to_stops_line
        )

        stops = gpd.GeoDataFrame.from_features(stib_stops.data["features"])
        stops["direction"] = stops["direction"] + 1  # Make direction 0 or 1

        # Create a new GeoDataFrame to store the segments
        segments = []

        # Iterate over the lines and directions
        for (line, variant), stops_for_line in stops.groupby(
                ["route_short_name", "direction"]
        ):
            line_geometry = shapefile[shapefile["ligne"] == line][
                shapefile["variante"] != variant
                ]

            segments_for_line_variant = self.process_all_segments_of_line_variant(
                line,
                line_geometry,
                stops_for_line,
                variant,
            )

            segments += segments_for_line_variant

        response_df = pd.DataFrame(segments)

        response_gdf = gpd.GeoDataFrame(
            response_df,
            crs="4326",
            geometry=response_df["geometry"],
        )

        response_gdf.set_index("start", inplace=True, drop=False)

        return json.loads(response_gdf.to_json())

    @staticmethod
    def process_all_segments_of_line_variant(
            line, line_geometry, stops_for_line, variant
    ):

        if line_geometry.empty:
            return []

        results = []

        line_string: LineString = line_geometry.iloc[0]["geometry"]

        line_string_belgian_lambert = transform(project.transform, line_string)

        previous_stop = None

        stop_to_stop_on_line = {}

        for _, stop in stops_for_line.iterrows():
            (
                line_string,
                point_for_stop,
            ) = STIBSegmentsHarvester.interpolate_stop_point_in_line_string(
                line_string, stop["geometry"]
            )

            stop_to_stop_on_line[stop["geometry"]] = point_for_stop

        line_coords = list(line_string.coords)

        for _, stop in stops_for_line.iterrows():
            if previous_stop is not None:
                stop_point = stop["geometry"]
                previous_stop_point = previous_stop["geometry"]
                _, end = STIBSegmentsHarvester.nearest_points(stop_point, line_string)
                _, start = STIBSegmentsHarvester.nearest_points(
                    previous_stop_point, line_string
                )

                best_start_point = None
                best_start_distance = None

                best_end_point = None
                best_end_distance = None

                for line_point in line_coords:
                    start_distance = start.distance(Point(line_point))
                    end_distance = end.distance(Point(line_point))

                    if (
                            best_start_distance is None
                            or start_distance < best_start_distance
                    ):
                        best_start_distance = start_distance
                        best_start_point = line_point

                    if best_end_distance is None or end_distance < best_end_distance:
                        best_end_distance = end_distance
                        best_end_point = line_point

                coords = line_coords[
                         line_coords.index(best_start_point): line_coords.index(
                             best_end_point
                         )
                                                              + 1
                         ]

                if len(coords) > 1:
                    segment = LineString(coords)
                    distance = line_string_belgian_lambert.project(
                        transform(project.transform, start)
                    )

                    results.append(
                        {
                            "line_id": line,
                            "direction": variant,
                            "geometry": segment,
                            "start": previous_stop["stop_id"],
                            "distance": distance,
                            "end": stop["stop_id"],
                            "color": line_geometry.iloc[0]["color_hex"],
                            # replace first character of color_hex with order of stop
                        }
                    )

            previous_stop = stop

        return results

    @staticmethod
    def nearest_points(g1, g2):
        """Returns the calculated nearest points in the input geometries

        The points are returned in the same order as the input geometries.
        """
        seq = shapely.shortest_line(g1, g2)
        if seq is None:
            if g1.is_empty:
                raise ValueError("The first input geometry is empty")
            else:
                raise ValueError("The second input geometry is empty")

        p1 = shapely.get_point(seq, 0)
        p2 = shapely.get_point(seq, 1)
        return (p1, p2)

    @staticmethod
    def interpolate_stop_point_in_line_string(line_string: LineString, point: Point):
        coords = list(line_string.coords)

        best_line_segment = None
        best_line_segment_distance = None

        for i in range(1, len(coords)):
            line_segment = LineString([coords[i - 1], coords[i]])

            distance = line_segment.distance(point)

            if best_line_segment is None or distance < best_line_segment_distance:
                best_line_segment = line_segment
                best_line_segment_distance = distance

        if best_line_segment is not None:
            point_on_line_segment = best_line_segment.interpolate(
                best_line_segment.project(point)
            )

            if point_on_line_segment:
                coords.insert(
                    coords.index(best_line_segment.coords[1]),
                    point_on_line_segment.coords[0],
                )

                return LineString(coords), point_on_line_segment.coords[0]
            else:
                return LineString(coords), point

        raise ValueError("No line segment found")
