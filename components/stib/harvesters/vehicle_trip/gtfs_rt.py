"""GTFS-RT feeds for STIB, which publishes none, built from `stib.vehicle_trip`.

Built on request by the handlers in stib/handlers/gtfs_rt.py, not stored: each
feed is a pure function of a `vehicle_trip` snapshot and the timetable.

VehiclePositions carries every tracked vehicle: with its trip where one was
established, and with only its route and direction where not (both are valid
GTFS-RT). TripUpdates carries one update per trip that has a vehicle on it: the
delay measured at the last stop the vehicle called at, applied to every stop
still ahead of it. Trips with no vehicle are left out rather than declared on
time, since "no vehicle seen" is not evidence of anything.
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd
from google.transit import gtfs_realtime_pb2

from ..punctuality import match
from .harvester import _tables

BRUSSELS = "Europe/Brussels"
_STATUS = {
    "STOPPED_AT": gtfs_realtime_pb2.VehiclePosition.STOPPED_AT,
    "IN_TRANSIT_TO": gtfs_realtime_pb2.VehiclePosition.IN_TRANSIT_TO,
}


def _vehicles(payload):
    if isinstance(payload, (bytes, bytearray, str)):
        payload = json.loads(payload)
    for feature in (payload or {}).get("features", ()):
        properties = dict(feature.get("properties") or {})
        properties["coordinates"] = (feature.get("geometry") or {}).get("coordinates")
        yield properties


def _feed(timestamp: float) -> gtfs_realtime_pb2.FeedMessage:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    feed.header.timestamp = int(timestamp)
    return feed


def _trip(descriptor, vehicle):
    if vehicle.get("tripId"):
        descriptor.trip_id = vehicle["tripId"]
        descriptor.start_date = vehicle["startDate"]
        descriptor.start_time = vehicle["startTime"]
        descriptor.schedule_relationship = gtfs_realtime_pb2.TripDescriptor.SCHEDULED
    if vehicle.get("routeId"):
        descriptor.route_id = vehicle["routeId"]
    if vehicle.get("direction") is not None:
        descriptor.direction_id = int(vehicle["direction"])


def vehicle_positions(payload) -> bytes:
    """A VehiclePositions feed from a `vehicle_trip` snapshot, or None."""
    vehicles = list(_vehicles(payload))
    if not vehicles:
        return None
    feed = _feed(max(v["timestamp"] for v in vehicles))
    for vehicle in vehicles:
        if not vehicle.get("coordinates"):
            continue
        entity = feed.entity.add()
        entity.id = vehicle["uuid"]
        position = entity.vehicle
        _trip(position.trip, vehicle)
        position.vehicle.id = vehicle["uuid"]
        position.vehicle.label = str(vehicle["lineId"])
        position.position.longitude, position.position.latitude = vehicle["coordinates"]
        if vehicle.get("stopId"):
            position.stop_id = vehicle["stopId"]
            position.current_stop_sequence = int(vehicle["stopSequence"])
        if vehicle.get("status"):
            position.current_status = _STATUS[vehicle["status"]]
        position.timestamp = int(vehicle["timestamp"])
    return feed.SerializeToString()


class _StopTimes:
    """The timetable's stop times, sliced per trip."""

    def __init__(self, gtfs: dict):
        times = gtfs["stop_times"].sort_values(["trip_id", "stop_sequence"])
        self.trip = times.trip_id.astype(str).values
        self.stop = times.stop_id.astype(str).values
        self.sequence = times.stop_sequence.astype(int).values
        self.arrival = pd.to_timedelta(times.arrival_time).dt.total_seconds().values
        self.departure = pd.to_timedelta(times.departure_time).dt.total_seconds().values
        starts = np.flatnonzero(np.r_[True, self.trip[1:] != self.trip[:-1]])
        ends = np.r_[starts[1:], len(self.trip)]
        self.index = {self.trip[a]: (a, b) for a, b in zip(starts, ends)}


_stop_times = {"date": None, "table": None}


def _midnight(service_date: str) -> float:
    """The origin GTFS times of `service_date` count from (noon minus 12h)."""
    return match.service_day_origin(datetime.strptime(service_date, "%Y%m%d")).timestamp()


def trip_updates(payload, stib_gtfs_parquet) -> bytes:
    """A TripUpdates feed from a `vehicle_trip` snapshot and the `gtfs_parquet`
    row in force at that moment, or None."""
    if _stop_times["date"] != stib_gtfs_parquet.date:
        _stop_times["table"] = _StopTimes(_tables(stib_gtfs_parquet.data))
        _stop_times["date"] = stib_gtfs_parquet.date
    table = _stop_times["table"]

    vehicles = [v for v in _vehicles(payload) if v.get("tripId") and v.get("delay") is not None]
    if not vehicles:
        return None
    feed = _feed(max(v["timestamp"] for v in vehicles))
    for vehicle in vehicles:
        span = table.index.get(vehicle["tripId"])
        if span is None:
            continue
        a, b = span
        # From the stop the vehicle is at or heading to; with none known,
        # from the first stop scheduled after the moment of the poll.
        midnight = _midnight(vehicle["startDate"])
        if vehicle.get("stopSequence") is not None:
            first = a + int(np.searchsorted(table.sequence[a:b], int(vehicle["stopSequence"])))
        else:
            first = a + int(np.searchsorted(table.arrival[a:b] + midnight + vehicle["delay"],
                                            vehicle["timestamp"]))
        if first >= b:
            continue
        delay = int(vehicle["delay"])
        entity = feed.entity.add()
        entity.id = f"{vehicle['tripId']}-{vehicle['startDate']}"
        update = entity.trip_update
        _trip(update.trip, vehicle)
        update.vehicle.id = vehicle["uuid"]
        update.vehicle.label = str(vehicle["lineId"])
        update.timestamp = int(vehicle["timestamp"])
        update.delay = delay
        for i in range(first, b):
            stop = update.stop_time_update.add()
            stop.stop_sequence = int(table.sequence[i])
            stop.stop_id = table.stop[i]
            stop.arrival.delay = delay
            stop.arrival.time = int(midnight + table.arrival[i] + delay)
            stop.departure.delay = delay
            stop.departure.time = int(midnight + table.departure[i] + delay)
            stop.schedule_relationship = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SCHEDULED
    return feed.SerializeToString() if feed.entity else None
