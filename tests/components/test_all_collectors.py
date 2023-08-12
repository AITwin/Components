import unittest

from dotenv import load_dotenv

from src.configuration.load import load_all_components


class TestCollectors(unittest.TestCase):
    # Initialize the test class
    def setUp(self):
        load_dotenv()
        self.collector_classes = list(load_all_components().collectors.values())

    def test_collector_output_types(self):
        for collector_class in self.collector_classes:
            collector_instance = collector_class.component()

            output = collector_instance.run()

            if collector_class.data_type == "json":
                expected_output_type = dict
            elif collector_class.data_type == "binary":
                expected_output_type = bytes
            else:
                expected_output_type = str

            self.assertIsInstance(output, expected_output_type)
