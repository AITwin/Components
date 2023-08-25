import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from src.components import Harvester
from src.data.retrieve import retrieve_latest_row, retrieve_between_datetime


class DailyPredictorHarvester(Harvester):
    def run(self, source, bolt_count):
        final_df = self.process_data(source, bolt_count)

        final_df.to_csv(f"final_df_test_{ source[-1].date}.csv")
        return {"test": "test"}

    def process_data(self, new_aggregates, old_aggregates):
        new_df = self.create_dateframe(new_aggregates)
        old_df = self.create_dateframe(old_aggregates)
        all_df = pd.concat([new_df, old_df])
        return all_df

    def create_dateframe(self, aggregates):
        source_df = pd.DataFrame()
        for json_data in aggregates:
            data = json_data.data
            list_of_dicts = [
                {
                    "key": outer_key,
                    "ebike_availibility": inner_dict["ebike_availibility"],
                }
                for outer_key, inner_dict in data.items()
            ]

            df = pd.DataFrame(list_of_dicts)
            df["timestamp"] = json_data.date
            source_df = pd.concat([source_df, df])
        return source_df
