"""Voi collectors: skip cleanly without a feed URL, read GBFS 2 and 3 discovery files."""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.micromobility.voi import gbfs  # noqa: E402
from components.micromobility.voi.collectors.geofence import VoiGeofenceCollector  # noqa: E402
from components.micromobility.voi.collectors.vehicle_position import (  # noqa: E402
    VoiVehiclePositionCollector,
)
from components.micromobility.voi.collectors.vehicle_type import VoiVehicleTypeCollector  # noqa: E402

DISCOVERY_V2 = {"data": {"en": {"feeds": [
    {"name": "free_bike_status", "url": "https://voi.test/free_bike_status"},
    {"name": "vehicle_types", "url": "https://voi.test/vehicle_types"},
    {"name": "geofencing_zones", "url": "https://voi.test/geofencing_zones"},
]}}}
DISCOVERY_V3 = {"data": {"feeds": [
    {"name": "vehicle_status", "url": "https://voi.test/vehicle_status"},
]}}
BIKES = {"data": {"bikes": [
    {"bike_id": "a", "lat": 50.85, "lon": 4.35, "vehicle_type_id": "scooter", "is_reserved": False, "is_disabled": False},
    {"bike_id": "b", "lat": 50.84, "lon": 4.36, "vehicle_type_id": "bike", "is_reserved": False, "is_disabled": False},
]}}
ZONES = {"data": {"geofencing_zones": {"type": "FeatureCollection", "features": []}}}


def _server(pages):
    def get(url):
        return pages[url]
    return get


class WithoutConfiguration(unittest.TestCase):
    def test_collectors_store_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOI_GBFS_URL", None)
            for collector in (VoiVehiclePositionCollector, VoiGeofenceCollector, VoiVehicleTypeCollector):
                self.assertIsNone(collector().run())


class WithFeed(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"VOI_GBFS_URL": "https://voi.test/gbfs.json"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_vehicle_positions_are_geojson_like_dott_and_bolt(self):
        pages = {"https://voi.test/gbfs.json": DISCOVERY_V2, "https://voi.test/free_bike_status": BIKES}
        with mock.patch.object(gbfs, "_get", _server(pages)):
            result = VoiVehiclePositionCollector().run()
        self.assertEqual(result["type"], "FeatureCollection")
        self.assertEqual(len(result["features"]), 2)
        feature = result["features"][0]
        self.assertEqual(feature["geometry"], {"type": "Point", "coordinates": [4.35, 50.85]})
        self.assertNotIn("lat", feature["properties"])
        self.assertEqual(feature["properties"]["bike_id"], "a")

    def test_gbfs3_vehicle_status_is_used(self):
        v3 = {"data": {"vehicles": [{"vehicle_id": "x", "lat": 50.8, "lon": 4.4}]}}
        pages = {"https://voi.test/gbfs.json": DISCOVERY_V3, "https://voi.test/vehicle_status": v3}
        with mock.patch.object(gbfs, "_get", _server(pages)):
            result = VoiVehiclePositionCollector().run()
        self.assertEqual(result["features"][0]["properties"]["vehicle_id"], "x")

    def test_station_only_vehicles_are_skipped(self):
        docked = {"data": {"bikes": [{"bike_id": "s", "station_id": "st1"}, BIKES["data"]["bikes"][0]]}}
        only_docked = {"data": {"bikes": [{"bike_id": "s", "station_id": "st1"}]}}
        for feed, count in ((docked, 1), (only_docked, 0)):
            pages = {"https://voi.test/gbfs.json": DISCOVERY_V2, "https://voi.test/free_bike_status": feed}
            with mock.patch.object(gbfs, "_get", _server(pages)):
                self.assertEqual(len(VoiVehiclePositionCollector().run()["features"]), count)

    def test_geofences(self):
        pages = {"https://voi.test/gbfs.json": DISCOVERY_V2, "https://voi.test/geofencing_zones": ZONES}
        with mock.patch.object(gbfs, "_get", _server(pages)):
            self.assertEqual(VoiGeofenceCollector().run(), ZONES["data"]["geofencing_zones"])

    def test_missing_feed_fails_loudly(self):
        with mock.patch.object(gbfs, "_get", _server({"https://voi.test/gbfs.json": DISCOVERY_V3})):
            with self.assertRaises(KeyError):
                VoiGeofenceCollector().run()

    def test_token_is_sent_as_bearer(self):
        with mock.patch.dict(os.environ, {"VOI_GBFS_TOKEN": "secret"}):
            self.assertEqual(gbfs._headers(), {"Authorization": "Bearer secret"})


if __name__ == "__main__":
    unittest.main()
