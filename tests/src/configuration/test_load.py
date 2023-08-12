import unittest

from components.stib.collectors.vehicle_distance import STIBVehiclePositionsCollector
from src.components import Collector
from src.configuration.load import (
    class_from_path,
    load_all_components,
    get_optimal_dependencies_wise_order,
    _treat_name,
)
from src.configuration.model import ComponentConfiguration


class TestConfiguration(unittest.TestCase):
    def test_class_from_path(self):
        class_p = class_from_path(
            "stib.collectors.vehicle_distance.STIBVehiclePositionsCollector"
        )
        self.assertEqual(class_p.__name__, STIBVehiclePositionsCollector.__name__)

    def test_load_all_components(self):
        load_all_components()

    def test_get_optimal_dependencies_wise_order(self):
        fake_args = {
            "data_type": "data_type",
            "data_format": "data_format",
            "dependencies": [],
            "dependencies_limit": [],
            "component": Collector,
            "schedule": "",
            "source_range": "",
            "source": "",
        }
        harvester1 = ComponentConfiguration(
            name="harvester1",
            **fake_args,
        )
        harvester2 = ComponentConfiguration(name="harvester2", **fake_args)
        harvester3 = ComponentConfiguration(name="harvester3", **fake_args)
        harvester4 = ComponentConfiguration(name="harvester4", **fake_args)
        harvester1.dependencies = [harvester2, harvester3]
        harvester2.dependencies = [harvester3]
        harvester4.dependencies = [harvester2]

        harvesters = {
            "harvester1": harvester1,
            "harvester2": harvester2,
            "harvester3": harvester3,
            "harvester4": harvester4,
        }

        result = get_optimal_dependencies_wise_order(harvesters)
        self.assertEqual(result, [harvester3, harvester2, harvester1, harvester4])

    def test_treat_name(self):
        file_name = "file1"
        source = "source_name"

        result = _treat_name(file_name, source)

        self.assertEqual(result, "file1_source_name")
