import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from src.components import Harvester
from src.data.retrieve import retrieve_latest_row, retrieve_between_datetime
from alibi_detect.od import OutlierProphet
import pytz
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore", category=RuntimeWarning)

class DailyPredictorHarvester(Harvester):
    def run(self, source, bolt_count, storage_date, **kwargs):
        final_dataframe = self.create_dataframe(bolt_count)
        test_dataframe = self.create_test_dataframe(storage_date)
        final_test_dataframe = pd.DataFrame()
        
        for area_id in final_dataframe["area_id"].drop_duplicates().to_list():
            temporary_df = final_dataframe[final_dataframe.area_id == area_id]
            train_data = temporary_df.reset_index(drop=True)
            model = self.train_model(train_data[["ds", "y"]].copy())
            detected_data = self.detect_outliers(model, test_dataframe)
            temporary_df = detected_data
            temporary_df["area_id"] = area_id
            final_test_dataframe = pd.concat([final_test_dataframe, temporary_df])
        
        final_test_dataframe["ds"] = final_test_dataframe["ds"].dt.strftime("%Y/%m/%d %H:%M:%S")
        
        result = (
            final_test_dataframe.groupby(["ds", "area_id"])
            .agg(
                pred=("pred", "first"),
                pred_upper=("pred_upper", "first"),
                pred_lower=("pred_lower", "first"),
            )
            .reset_index()
            .groupby("ds")
            .apply(
                lambda group: {
                    str(area_id): group.set_index("area_id")
                    .drop(columns=["ds"])
                    .to_dict(orient="index")
                }
            )
            .to_dict()
        )
        
        return result

    def create_dataframe(self, aggregates):
        source_dataframe = pd.DataFrame()

        for json_data in aggregates:
            data = json_data.data
            list_of_dicts = [
                {
                    "area_id": outer_key,
                    "y": inner_dict["ebike_availibility"],
                }
                for outer_key, inner_dict in data.items()
            ]

            df = pd.DataFrame(list_of_dicts)

            df["ds"] = json_data.date
            source_dataframe = pd.concat([source_dataframe, df])
        return source_dataframe

    def create_test_dataframe(self, minimum_time):
        test_dataframe = pd.DataFrame()
        test_dataframe["ds"] = pd.date_range(
            minimum_time, minimum_time + timedelta(days=1, hours=12), freq="15min"
        )
        test_dataframe["y"] = 0
        return test_dataframe

    def train_model(self, train_data):
        train_data.sort_values("ds", inplace=True)
        model = OutlierProphet(
            threshold=0.95,
            daily_seasonality=True,
            weekly_seasonality=True,
            seasonality_mode="additive",
            growth="linear",
        )
        model.fit(train_data)
        return model

    def detect_outliers(self, model, test_data):
        result = model.predict(test_data, return_instance_score=True, return_forecast=True)
        test_data["pred"] = result["data"]["forecast"]["yhat"]
        test_data["pred_upper"] = result["data"]["forecast"]["yhat_upper"]
        test_data["pred_lower"] = result["data"]["forecast"]["yhat_lower"]
        return test_data
