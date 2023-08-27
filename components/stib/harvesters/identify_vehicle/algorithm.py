import copy
import uuid
from dataclasses import dataclass
from itertools import product
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression

from components.stib.utils.constant import METRO, TRAM

MAXIMUM_GAP_TIME = 60 * 5  # 5 minutes

MAXIMUM_BACKWARD_DISTANCE = 40  # meters

STALE_PENALTY = 2

METRO_LINE_IDS = list(map(str, METRO))

TRAM_LINE_IDS = list(map(str, TRAM))


def get_max_speed_for_line(line_id):
    if line_id in METRO_LINE_IDS:
        return 250  # Metro skips points

    if line_id in TRAM_LINE_IDS:
        return 60

    return 80


@dataclass
class Point:
    timestamp: int
    distance: float
    line: str
    row: pd.Series = None

    def __hash__(self):
        return hash((self.timestamp, self.distance, self.line))

    def __eq__(self, other):
        return (
            self.timestamp == other.timestamp
            and self.distance == other.distance
            and self.line == other.line
        )


def get_line_type(line_id):
    if line_id in METRO_LINE_IDS:
        return "metro"

    if line_id in TRAM_LINE_IDS:
        return "tram"

    return "bus"


STALE_THRESHOLD = 0  # Set a threshold to determine if a point is stale


class Trip:
    def __init__(self, line, distance_scale, vehicle_id=None):
        self.distance_scale = distance_scale

        self.points = []

        if vehicle_id is None:
            self.vehicle_id = str(uuid.uuid4())
        else:
            self.vehicle_id = vehicle_id

        self.line = line

        self.line_type = get_line_type(line)

    def __hash__(self):
        return hash((self.vehicle_id, self.line))

    def add_point(self, point):
        self.points.append(point)


def vehicle_point_from_row(row):
    return Point(row["timestamp"], row["distance"], str(row["lineId"]), row)


class IdentifyVehicleAlgorithm:
    def __init__(self, dataframe: pd.DataFrame, line: str):
        self.line = line

        dataframe = dataframe.reset_index(drop=True)

        # Order by timestamp (oldest first) and by distance (biggest first)
        dataframe = dataframe.sort_values(by=["timestamp"])

        self.min_timestamp = dataframe["timestamp"].min()
        self.min_distance = dataframe["distance"].min()

        self.timestamp_normalized_scale = (
            dataframe["timestamp"].max() - dataframe["timestamp"].min()
        )

        self.distance_normalized_scale = (
            dataframe["distance"].max() - dataframe["distance"].min()
        )

        # Normalize the timestamps on a 0-1 scale
        dataframe["timestamp"] = (
            dataframe["timestamp"] - self.min_timestamp
        ) / self.timestamp_normalized_scale if self.timestamp_normalized_scale else 0

        # Normalize the distance on a 0-1 scale
        dataframe["distance"] = (
            ((dataframe["distance"] - self.min_distance) / self.distance_normalized_scale)
            if self.distance_normalized_scale
            else 0
        )

        # Available points are point without uuid
        self.available_points = [
            vehicle_point_from_row(row)
            for _, row in dataframe[dataframe["uuid"].isnull()].iterrows()
        ]

        self.trips = []

        for vehicle_id, data_for_line_id in dataframe.groupby("uuid"):
            self.trips.append(
                Trip(
                    line=self.line,
                    vehicle_id=vehicle_id,
                    distance_scale=self.distance_normalized_scale,
                )
            )
            for _, row in data_for_line_id.iterrows():
                self.trips[-1].add_point(vehicle_point_from_row(row))

    def match_iter(self):
        usable_points = list(copy.deepcopy(self.available_points))

        if len(self.trips) == 0:
            # Create trips for all the points at first timestamp
            for point in usable_points:
                if point.timestamp == 0:
                    self.trips.append(
                        Trip(
                            line=self.line,
                            vehicle_id=str(uuid.uuid4()),
                            distance_scale=self.distance_normalized_scale,
                        )
                    )
                    self.trips[-1].add_point(point)
                    usable_points.remove(point)

        while len(usable_points) > 0:
            scores_for_trips: Dict[Tuple[Point, Trip], float] = {}

            # Iterate over each available point and each trip to find the best match.
            for point, trip in product(usable_points, self.trips):
                if self.can_be_matched_to_trip(point, trip):
                    scores_for_trips[(point, trip)] = self.get_score_for_point_for_trip(
                        point, trip
                    )

            # Find the best match
            if len(scores_for_trips) == 0:
                trips_best_match = None
            else:
                trips_best_match = min(scores_for_trips, key=scores_for_trips.get)

            if trips_best_match:
                point, trip = trips_best_match
                trip.add_point(point)
                usable_points.remove(point)
            else:
                # Add a new trip with the first available point
                self.trips.append(Trip(self.line, self.distance_normalized_scale))
                self.trips[-1].add_point(usable_points[0])
                usable_points.remove(usable_points[0])

        # Only if not metro
        if get_line_type(self.line) != "metro":
            self.split_strange_trips()

        self.merge_trips()

    def is_trip_stale(self, trip):
        # Must at least have 5 points before even considering it
        if len(trip.points) < 5:
            return False

        total_distance = trip.points[-1].distance - trip.points[0].distance

        if total_distance * self.distance_normalized_scale < STALE_THRESHOLD:
            return True

        return False

    def can_be_matched_to_trip(self, point, trip):
        can_be_matched = True

        # Check if point timestamp is indeed after the last point of the trip
        if trip.points[-1].timestamp >= point.timestamp:
            can_be_matched = False

        # Check if the timestamp is not too far in the future
        if (
            point.timestamp - trip.points[-1].timestamp
        ) * self.timestamp_normalized_scale > trip.points[
            -1
        ].timestamp + MAXIMUM_GAP_TIME:
            can_be_matched = False

        # Ensure not too much backward movement
        if (
            point.distance - trip.points[-1].distance
            < -MAXIMUM_BACKWARD_DISTANCE / (self.distance_normalized_scale or 1)
        ):
            can_be_matched = False

        time_diff = (
            point.timestamp - trip.points[-1].timestamp
        ) * self.timestamp_normalized_scale
        distance_diff = (
            point.distance - trip.points[-1].distance
        ) * self.distance_normalized_scale

        if time_diff == 0:
            return False

        speed_between_points = distance_diff / time_diff if time_diff > 0 else 0

        if speed_between_points > get_max_speed_for_line(self.line):
            can_be_matched = False

        return can_be_matched

    def split_strange_trips(self):
        new_trips = []
        for trip in self.trips:
            speeds = []
            points = []

            # Compute average speed between each point
            for point1, point2 in zip(trip.points[:-1], trip.points[1:]):
                time_diff = (
                    point2.timestamp - point1.timestamp
                ) * self.timestamp_normalized_scale
                distance_diff = (
                    point2.distance - point1.distance
                ) * self.distance_normalized_scale

                points.append(point2)

                if time_diff > 0:
                    speed_between_points = distance_diff / time_diff

                    if speed_between_points > 0:
                        speeds.append(speed_between_points)
                        continue
                speeds.append(0)

            z_scores = stats.zscore(speeds)

            points_to_split = []

            for index, z_score in enumerate(z_scores):
                if abs(z_score) > 4:
                    points_to_split.append((points[index], index))
            # Create two new trips if both would have at least 2 points
            for point, index in points_to_split:
                new_trip = Trip(self.line, self.distance_normalized_scale)
                new_trip.points = trip.points[index:]

                if len(new_trip.points) < 3:
                    continue
                if len(trip.points[:index]) < 3:
                    continue
                trip.points = trip.points[:index]
                new_trips.append(new_trip)

        self.trips.extend(new_trips)

    def merge_trips(self):
        trips_to_merge = {}

        for trip1, trip2 in product(self.trips, self.trips):
            if trip1 == trip2:
                continue

            if self.are_trips_mergeable(trip1, trip2):
                trips_to_merge[(trip1, trip2)] = self.score_for_trips(trip1, trip2)

        # For each trip pair, find the best match
        while len(trips_to_merge) > 0:
            best_match = min(trips_to_merge, key=trips_to_merge.get)
            trip1, trip2 = best_match
            self.merge_trips_together(trip1, trip2)
            trips_to_merge = {
                key: value
                for key, value in trips_to_merge.items()
                if key[0] != trip1
                and key[0] != trip2
                and key[1] != trip1
                and key[1] != trip2
            }

    @staticmethod
    def score_for_trips(trip_1, trip_2):
        return abs(trip_1.points[-1].distance - trip_2.points[0].distance)

    def are_trips_mergeable(self, trip1, trip2):
        # Make sure there are no overlapping points
        if trip1.points[-1].timestamp > trip2.points[0].timestamp:
            return False

        # Make sure there is at least two points in each trip
        if len(trip1.points) < 2 or len(trip2.points) < 2:
            return False

        # If last point is close enough to the first point of the next trip, merge them
        time_delta = (
            trip2.points[0].timestamp - trip1.points[-1].timestamp
        ) * self.timestamp_normalized_scale
        distance_delta = (
            trip2.points[0].distance - trip1.points[-1].distance
        ) * self.distance_normalized_scale

        if distance_delta < -MAXIMUM_BACKWARD_DISTANCE:
            return False

        if (
            time_delta < MAXIMUM_GAP_TIME
            and distance_delta / (time_delta or 1) < get_max_speed_for_line(self.line)
        ):
            return True

        x1 = [point.timestamp for point in trip1.points]
        y1 = [point.distance for point in trip1.points]

        x2 = [point.timestamp for point in trip2.points]
        y2 = [point.distance for point in trip2.points]

        # Fit the linear regression model
        model = LinearRegression().fit(np.array(x1).reshape(-1, 1), y1)

        # Predict y values for x2
        y_pred = model.predict(np.array(x2).reshape(-1, 1))

        # Calculate the residuals
        residuals = np.array(y1) - model.predict(np.array(x1).reshape(-1, 1)).ravel()

        # Calculate the standard error of residuals
        se_residuals = np.std(residuals)

        # Calculate the t value for the given confidence level
        confidence_interval = 0.75
        t = stats.t.ppf((1 + confidence_interval) / 2.0, len(y1) - 1)

        # Calculate the confidence intervals
        ci = (
            t
            * se_residuals
            * np.sqrt(
                1 / len(y1)
                + (np.array(x2) - np.mean(x1)) ** 2
                / np.sum((np.array(x1) - np.mean(x1)) ** 2)
            )
        )

        # Check if the actual y values of x2 fall within the confidence intervals
        are_on_line = [
            (y_pred[i] - ci[i]) <= y2[i] <= (y_pred[i] + ci[i]) for i in range(len(x2))
        ]

        return all(are_on_line)

    @staticmethod
    def get_linear_regression_for_trip(trip):
        x = [point.timestamp for point in trip.points]
        y = [point.distance for point in trip.points]

        linear_regression = LinearRegression()
        linear_regression.fit(np.array(x).reshape(-1, 1), y)

        return linear_regression.coef_[0], linear_regression.intercept_

    def get_score_for_point_for_trip(self, point, trip):
        distance_to_line = abs(trip.points[-1].distance - point.distance)

        # Add timestamp penalty
        distance_to_line += point.timestamp - trip.points[-1].timestamp

        if self.is_trip_stale(trip):
            distance_to_line *= STALE_PENALTY

        return distance_to_line

    def get_result(self):
        rows = []
        for line in self.trips:
            for point in line.points:
                point.row["uuid"] = line.vehicle_id
                rows.append(point.row)
                # Convert back normalized timestamp to original timestamp and distance
                point.row["timestamp"] = (
                    point.timestamp * self.timestamp_normalized_scale
                    + self.min_timestamp
                )
                point.row["distance"] = (
                    point.distance * self.distance_normalized_scale + self.min_distance
                )

        output_df = pd.DataFrame(rows).copy().sort_values(by=["timestamp"])

        return output_df

    def plot_lines(self):
        plt.figure()

        for line in self.trips:
            timestamps = [point.timestamp for point in line.points]
            distances = [point.distance for point in line.points]

            # Plot with an opacity of 0.5
            plt.plot(
                timestamps,
                distances,
                marker="+",
                label=line.vehicle_id,
                markersize=5,
            )

        # plt.legend()
        plt.xlabel("Timestamp")
        plt.ylabel("Distance")

        plt.show()

    def merge_trips_together(self, trip1, trip2):
        trip1.points.extend(trip2.points)
        self.trips.remove(trip2)
