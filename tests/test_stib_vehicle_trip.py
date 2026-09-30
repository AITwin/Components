"""STIB live vehicle trips and the GTFS-RT feeds built from them.

A small line in a synthetic timetable: four stops 500 m apart, one trip every
ten minutes, and a vehicle that runs it two minutes late.
"""
import io
import os
import sys
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

import pandas as pd

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.transit import gtfs_realtime_pb2  # noqa: E402

from components.stib.harvesters.vehicle_trip import (  # noqa: E402
    STIBVehicleTripHarvester, trip_updates, vehicle_positions, harvester as harvester_module,
)
from components.stib.harvesters.vehicle_trip.live import LiveTracker, _deviation, _pair  # noqa: E402

DAY = "20260929"
STOPS = ["1001", "1002", "1003", "1004"]
HOP = 500


def _gtfs() -> dict:
    trips, times = [], []
    for n in range(12):                                   # 08:00 .. 09:50 local
        trip = f"T{n:02d}"
        trips.append({"route_id": "R7", "service_id": "S", "trip_id": trip,
                      "direction_id": 0, "trip_headsign": "END"})
        for i, stop in enumerate(STOPS):
            t = pd.Timedelta(hours=8, minutes=10 * n + 2 * i)
            times.append({"trip_id": trip, "arrival_time": t, "departure_time": t,
                          "stop_id": stop, "stop_sequence": i + 1})
    return {
        "routes": pd.DataFrame([{"route_id": "R7", "route_short_name": "7", "route_type": 0,
                                 "route_color": "E4B000"}]),
        "trips": pd.DataFrame(trips),
        "stop_times": pd.DataFrame(times),
        "stops": pd.DataFrame([{"stop_id": s, "stop_name": s, "stop_lat": 50.85,
                                "stop_lon": 4.35 + 0.007 * i} for i, s in enumerate(STOPS)]),
        "calendar": pd.DataFrame([{"service_id": "S", "monday": 1, "tuesday": 1, "wednesday": 1,
                                   "thursday": 1, "friday": 1, "saturday": 1, "sunday": 1,
                                   "start_date": pd.Timestamp("2026-01-01"),
                                   "end_date": pd.Timestamp("2026-12-31")}]),
        "calendar_dates": pd.DataFrame(columns=["service_id", "date", "exception_type"]),
    }


def _zip(gtfs: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, frame in gtfs.items():
            out = io.BytesIO()
            frame.to_parquet(out, index=False)
            zf.writestr(f"{name}.parquet", out.getvalue())
    return buf.getvalue()


def _utc(hour, minute, second=0):
    # 08:00 in Brussels on 2026-09-29 is 06:00 UTC.
    return datetime(2026, 9, 29, hour - 2, minute, second)


def _position(metres):
    """The feed row of a vehicle `metres` along the line, running to the end."""
    index = min(int(metres // HOP), len(STOPS) - 1)
    return {"lineId": "7", "directionId": STOPS[-1], "pointId": STOPS[index],
            "distanceFromPoint": int(metres - index * HOP)}


def _polls(start, end, late_minutes=2):
    """Polls every 20 s of one vehicle running trip T03 (08:30) this late."""
    t = start
    while t <= end:
        departure = _utc(8, 30) + timedelta(minutes=late_minutes)
        metres = max(0.0, (t - departure).total_seconds()) * HOP / 120.0
        yield t, ([_position(metres)] if metres < HOP * (len(STOPS) - 1) else [])
        t += timedelta(seconds=20)


class _Row:
    def __init__(self, date, data):
        self.date = date
        self.data = data


class Pairing(unittest.TestCase):
    def test_unpaired_when_every_trip_is_too_far(self):
        import numpy as np
        costs = np.array([[1.0, np.inf], [np.inf, np.inf]])
        self.assertEqual(_pair(costs, 7.0), [(0, 0)])

    def test_total_deviation_decides_not_order(self):
        import numpy as np
        # Vehicle 0 fits trip 1 best and vehicle 1 fits trip 0 best.
        costs = np.array([[5.0, 0.5], [0.5, 5.0]])
        self.assertEqual(sorted(_pair(costs, 7.0)), [(0, 1), (1, 0)])


    def test_running_early_costs_more_than_running_late(self):
        calls = [("A", 1000), ("B", 1100)]
        late = _deviation(calls, {"A": [880], "B": [980]})    # 2 min late
        early = _deviation(calls, {"A": [1120], "B": [1220]})  # 2 min early
        self.assertAlmostEqual(late, 2.0)
        self.assertGreater(early, late)


class Tracker(unittest.TestCase):
    def test_vehicle_gets_its_trip_and_delay(self):
        tracker = LiveTracker(_gtfs())
        out = None
        for when, rows in _polls(_utc(8, 31), _utc(8, 38)):
            stamp = when.replace(tzinfo=__import__("datetime").timezone.utc).timestamp()
            frame = pd.DataFrame([{"line_id": r["lineId"], "direction_id": r["directionId"],
                                   "point_id": r["pointId"], "distance_from_point": r["distanceFromPoint"]}
                                  for r in rows], columns=["line_id", "direction_id", "point_id",
                                                           "distance_from_point"])
            out = tracker.step(frame, stamp) or out
        self.assertEqual(len(out), 1)
        vehicle = out[0]
        self.assertEqual(vehicle["tripId"], "T03")
        self.assertEqual(vehicle["startDate"], DAY)
        self.assertEqual(vehicle["startTime"], "08:30:00")
        self.assertEqual(vehicle["routeId"], "R7")
        self.assertAlmostEqual(vehicle["delay"], 120, delta=25)
        self.assertEqual(vehicle["color"], "#E4B000")


class Drawing(unittest.TestCase):
    """A branch 1001 -> 1002 -> 9001 runs beside the line to 1004, so the merged
    chain can list 9001 right after 1002."""

    def setUp(self):
        gtfs = _gtfs()
        gtfs["trips"] = pd.concat([gtfs["trips"], pd.DataFrame([{
            "route_id": "R7", "service_id": "S", "trip_id": "B01", "direction_id": 0,
            "trip_headsign": "BRANCH"}])], ignore_index=True)
        gtfs["stop_times"] = pd.concat([gtfs["stop_times"], pd.DataFrame([
            {"trip_id": "B01", "arrival_time": pd.Timedelta(hours=9, minutes=m),
             "departure_time": pd.Timedelta(hours=9, minutes=m), "stop_id": stop, "stop_sequence": i + 1}
            for i, (stop, m) in enumerate([("1001", 0), ("1002", 2), ("9001", 9)])])], ignore_index=True)
        gtfs["stops"] = pd.concat([gtfs["stops"], pd.DataFrame([{
            "stop_id": "9001", "stop_name": "9001", "stop_lat": 50.90, "stop_lon": 4.35}])],
            ignore_index=True)
        self.geometry = LiveTracker(gtfs).geometry

    def test_a_vehicle_heads_to_the_next_stop_of_its_own_pattern(self):
        lon, lat = self.geometry.position("7", 0, "1002", 250, "1004")
        self.assertAlmostEqual(lat, 50.85, places=4)
        self.assertGreater(lon, 4.357)
        lon, lat = self.geometry.position("7", 0, "1002", 250, "9001")
        self.assertGreater(lat, 50.86)

    def test_a_vehicle_past_its_terminus_stays_drawn_there(self):
        self.assertEqual(tuple(self.geometry.position("7", 0, "1004", 120, "1004")),
                         (4.35 + 0.007 * 3, 50.85))


class Relabelled(unittest.TestCase):
    """STIB relabels a metro train's destination mid-run (another platform id of
    the same terminus, or a short working); on such lines the train must keep
    its identity."""

    def _uuids(self, merged):
        from components.stib.harvesters.vehicle_trip import live
        original = live.ANY_DESTINATION_LINES
        live.ANY_DESTINATION_LINES = frozenset({"7"}) if merged else frozenset()
        self.addCleanup(setattr, live, "ANY_DESTINATION_LINES", original)
        tracker = LiveTracker(_gtfs())
        uuids = set()
        for n, (when, rows) in enumerate(_polls(_utc(8, 31), _utc(8, 35))):
            for row in rows:
                row["directionId"] = STOPS[-1] if n < 6 else STOPS[-2]   # relabelled at the 7th poll
            stamp = when.replace(tzinfo=timezone.utc).timestamp()
            frame = pd.DataFrame([{"line_id": r["lineId"], "direction_id": r["directionId"],
                                   "point_id": r["pointId"], "distance_from_point": r["distanceFromPoint"]}
                                  for r in rows], columns=["line_id", "direction_id", "point_id", "distance_from_point"])
            for vehicle in tracker.step(frame, stamp) or []:
                uuids.add(vehicle["uuid"])
        return uuids

    def test_a_relabelled_train_keeps_its_identity(self):
        self.assertEqual(len(self._uuids(merged=True)), 1)

    def test_lines_keyed_by_destination_start_a_new_track(self):
        self.assertEqual(len(self._uuids(merged=False)), 2)


class ServiceDay(unittest.TestCase):
    def test_gtfs_times_count_from_noon_minus_twelve_hours(self):
        from components.stib.harvesters.punctuality.match import service_day_origin
        # On both clock-change days 08:00:00 in the timetable is 08:00 on the clock.
        for day in ("2026-10-25", "2027-03-28", "2026-09-29"):
            eight = service_day_origin(pd.Timestamp(day)) + pd.Timedelta(hours=8)
            self.assertEqual(eight.tz_convert("Europe/Brussels").hour, 8, day)


def _step_all(tracker, polls):
    out = []
    for when, rows in polls:
        stamp = when.replace(tzinfo=__import__("datetime").timezone.utc).timestamp()
        frame = harvester_module._poll(rows)
        out.append(tracker.step(frame, stamp))
    return out


class Terminus(unittest.TestCase):
    def test_a_vehicle_standing_at_its_last_stop_has_finished_its_trip(self):
        tracker = LiveTracker(_gtfs())
        polls = list(_polls(_utc(8, 31), _utc(8, 37)))
        # Then it stands at the terminus for five minutes.
        end = polls[-1][0]
        at_end = [{"lineId": "7", "directionId": STOPS[-1], "pointId": STOPS[-1], "distanceFromPoint": 0}]
        polls += [(end + timedelta(seconds=20 * k), at_end) for k in range(1, 16)]
        outs = _step_all(tracker, polls)
        self.assertEqual(outs[len(polls) - 16][0]["tripId"], "T03")
        self.assertIsNone(outs[-1][0]["tripId"])


class Restart(unittest.TestCase):
    def test_identity_survives_a_rebuild(self):
        harvester_module._state.update(tracker=None, timetable=None)
        gtfs_row = _Row(datetime(2026, 9, 29, 2, 20), _zip(_gtfs()))
        polls = list(_polls(_utc(8, 31), _utc(8, 37)))
        run = lambda i, history, previous=None: STIBVehicleTripHarvester().run(
            _Row(*polls[i]), gtfs_row, None, history, previous)
        first = run(10, [_Row(t, r) for t, r in reversed(polls[:10])])
        uuid = first["features"][0]["id"]
        # The process restarts: state gone, the previous snapshot is the dependency.
        harvester_module._state.update(tracker=None, timetable=None)
        again = run(11, [_Row(t, r) for t, r in reversed(polls[:11])], _Row(polls[10][0], first))
        self.assertEqual(again["features"][0]["id"], uuid)

    def test_empty_polls_keep_distances_numeric(self):
        frame = pd.concat([harvester_module._poll([]), harvester_module._poll([_position(10)])])
        self.assertEqual(frame.distance_from_point.dtype.kind, "i")


class Harvester(unittest.TestCase):
    def setUp(self):
        harvester_module._state.update(tracker=None, timetable=None)
        self.gtfs_row = _Row(datetime(2026, 9, 29, 2, 20), _zip(_gtfs()))

    def _run(self, when, rows, history):
        return STIBVehicleTripHarvester().run(_Row(when, rows), self.gtfs_row, None, history)

    def test_rebuilds_from_history_then_continues(self):
        polls = list(_polls(_utc(8, 31), _utc(8, 37)))
        history = [_Row(t, rows) for t, rows in reversed(polls[:-1])]   # newest first
        out = self._run(polls[-1][0], polls[-1][1], history)
        tracker = harvester_module._state["tracker"]
        self.assertEqual(out["features"][0]["properties"]["tripId"], "T03")
        # The next poll continues the same tracker rather than rebuilding.
        t = polls[-1][0] + timedelta(seconds=20)
        self._run(t, polls[-1][1], [])
        self.assertIs(harvester_module._state["tracker"], tracker)

    def test_gap_longer_than_a_track_forces_a_rebuild(self):
        polls = list(_polls(_utc(8, 31), _utc(8, 33)))
        self._run(polls[-1][0], polls[-1][1], [_Row(t, r) for t, r in reversed(polls[:-1])])
        first = harvester_module._state["tracker"]
        self._run(polls[-1][0] + timedelta(minutes=10), polls[-1][1], [])
        self.assertIsNot(harvester_module._state["tracker"], first)


def _vehicle_trip_payload(**overrides):
    properties = {
        "uuid": "u-1", "lineId": "7", "directionId": "1004", "direction": 0,
        "pointId": "1002", "distanceFromPoint": 120, "color": "#E4B000",
        "timestamp": _utc(8, 35).replace(tzinfo=__import__("datetime").timezone.utc).timestamp(),
        "tripId": "T03", "routeId": "R7", "startDate": DAY, "startTime": "08:30:00",
        "delay": 120, "status": "IN_TRANSIT_TO", "stopId": "1003", "stopSequence": 3,
    }
    properties.update(overrides)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "u-1", "properties": properties,
         "geometry": {"type": "Point", "coordinates": [4.36, 50.85]}}]}


class GTFSRT(unittest.TestCase):
    def test_vehicle_position(self):
        blob = vehicle_positions(_vehicle_trip_payload())
        feed = gtfs_realtime_pb2.FeedMessage.FromString(blob)
        vp = feed.entity[0].vehicle
        self.assertEqual(vp.trip.trip_id, "T03")
        self.assertEqual(vp.trip.start_date, DAY)
        self.assertEqual(vp.trip.route_id, "R7")
        self.assertEqual(vp.current_stop_sequence, 3)
        self.assertEqual(vp.stop_id, "1003")
        self.assertEqual(vp.current_status, gtfs_realtime_pb2.VehiclePosition.IN_TRANSIT_TO)
        self.assertAlmostEqual(vp.position.latitude, 50.85, places=4)

    def test_vehicle_without_trip_keeps_route_and_direction(self):
        payload = _vehicle_trip_payload(tripId=None, startDate=None, startTime=None,
                                        delay=None, stopId=None, stopSequence=None)
        feed = gtfs_realtime_pb2.FeedMessage.FromString(
            vehicle_positions(payload))
        trip = feed.entity[0].vehicle.trip
        self.assertEqual((trip.trip_id, trip.route_id, trip.direction_id), ("", "R7", 0))

    def test_trip_update_carries_delay_to_the_stops_ahead(self):
        gtfs_row = _Row(datetime(2026, 9, 29, 2, 20), _zip(_gtfs()))
        blob = trip_updates(_vehicle_trip_payload(), gtfs_row)
        update = gtfs_realtime_pb2.FeedMessage.FromString(blob).entity[0].trip_update
        self.assertEqual(update.trip.trip_id, "T03")
        self.assertEqual([s.stop_sequence for s in update.stop_time_update], [3, 4])
        scheduled = pd.Timestamp("2026-09-29 08:34", tz="Europe/Brussels").timestamp()
        self.assertEqual(update.stop_time_update[0].arrival.time, int(scheduled) + 120)
        self.assertEqual(update.stop_time_update[0].arrival.delay, 120)

    def test_no_stop_ahead_is_predicted_in_the_past(self):
        # Heading to stop 3 (08:34 + 2 min) but it is already 08:40: held up.
        gtfs_row = _Row(datetime(2026, 9, 29, 2, 20), _zip(_gtfs()))
        at = _utc(8, 40).replace(tzinfo=timezone.utc).timestamp()
        update = gtfs_realtime_pb2.FeedMessage.FromString(
            trip_updates(_vehicle_trip_payload(timestamp=at), gtfs_row)).entity[0].trip_update
        times = [(s.arrival.time, s.departure.time) for s in update.stop_time_update]
        self.assertTrue(all(a >= at and d >= a for a, d in times))
        self.assertEqual(update.stop_time_update[0].arrival.delay, int(at) - int(
            pd.Timestamp("2026-09-29 08:34", tz="Europe/Brussels").timestamp()))

    def test_standing_vehicle_arrived_in_the_past_but_has_not_left(self):
        gtfs_row = _Row(datetime(2026, 9, 29, 2, 20), _zip(_gtfs()))
        at = _utc(8, 40).replace(tzinfo=timezone.utc).timestamp()
        update = gtfs_realtime_pb2.FeedMessage.FromString(trip_updates(
            _vehicle_trip_payload(timestamp=at, status="STOPPED_AT"), gtfs_row)).entity[0].trip_update
        here = update.stop_time_update[0]
        self.assertLess(here.arrival.time, at)
        self.assertEqual(here.departure.time, int(at))

    def test_no_trip_update_without_a_delay(self):
        gtfs_row = _Row(datetime(2026, 9, 29, 2, 20), _zip(_gtfs()))
        payload = _vehicle_trip_payload(delay=None)
        self.assertIsNone(trip_updates(payload, gtfs_row))


if __name__ == "__main__":
    unittest.main()


class Handlers(unittest.TestCase):
    """The feeds are built on request from the snapshot in force."""

    def _handler(self, cls, rows):
        from components.stib.handlers import gtfs_rt as module

        class _Stub(cls):
            def get_table_by_name(self, name):
                return name

        def latest(table, date, limit):
            found = sorted((r for r in rows[table] if r.date < date), key=lambda r: r.date)
            return found[-1:]
        original, module.retrieve_latest_rows_before_datetime = module.retrieve_latest_rows_before_datetime, latest
        self.addCleanup(setattr, module, "retrieve_latest_rows_before_datetime", original)
        return _Stub({})

    def _rows(self):
        return {"stib_vehicle_trip": [_Row(_utc(8, 35), _vehicle_trip_payload())],
                "stib_gtfs_parquet": [_Row(datetime(2026, 9, 29, 2, 20), _zip(_gtfs()))]}

    def test_trip_updates_from_the_snapshot_in_force(self):
        from components.stib.handlers.gtfs_rt import STIBGTFSRTTripUpdateHandler
        at = _utc(8, 35, 10).replace(tzinfo=timezone.utc).timestamp()
        blob = self._handler(STIBGTFSRTTripUpdateHandler, self._rows()).run(at - 3600, at)
        feed = gtfs_realtime_pb2.FeedMessage.FromString(blob)
        self.assertEqual(feed.entity[0].trip_update.trip.trip_id, "T03")

    def test_no_feed_from_a_stale_snapshot(self):
        from components.stib.handlers.gtfs_rt import STIBGTFSRTVehiclePositionHandler
        at = _utc(8, 45).replace(tzinfo=timezone.utc).timestamp()
        self.assertIsNone(self._handler(STIBGTFSRTVehiclePositionHandler, self._rows()).run(at - 3600, at))
