import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from src.components import Harvester
from datetime import datetime


class AnomalyHarvester(Harvester):
    def run(self, sources, micromobility_area, bolt_daily_prediction, bolt_count, **kwargs):
        # Load the GeoDataFrame directly from the JSON data
        station_locations = gpd.GeoDataFrame.from_features(
            json.loads(micromobility_area.data)["features"], crs="EPSG:4326"
        )

        # Convert sources data to GeoDataFrame
        time_under_consideration = self.nearest_time(bolt_daily_prediction.data, sources[-1].date)
        ebike_dataframe = pd.json_normalize(sources[-1].data["features"])
        ebike_dataframe["geometry_point"] = ebike_dataframe["geometry.coordinates"].apply(Point)
        ebike_geodataframe = gpd.GeoDataFrame(ebike_dataframe, geometry="geometry_point", crs="EPSG:4326")

        # Perform the spatial join
        joined_dataframe = gpd.sjoin(station_locations, ebike_geodataframe, how="left", predicate="contains")

        # Group by poly_id and count occurrences
        aggregated_ebikes = joined_dataframe.groupby(["poly_id"])["properties.bike_id"].count().reset_index()
        aggregated_ebikes.rename(columns={"properties.bike_id": "ebike_availibility"}, inplace=True)

        last_24_hours_data = self.create_historical_dataframe(bolt_count)
  
        comparison_data = pd.DataFrame(bolt_daily_prediction.data[time_under_consideration])

        scores = self.calculate_anomaly_score(aggregated_ebikes, last_24_hours_data, comparison_data)

        # Convert the result to a dictionary
        result = scores[['area_id', 'ebike_availibility', 'anomaly', 'anomaly_score']].set_index("area_id").to_dict(orient = "index")
        
        return result

    def nearest_time(self, predictions, target_time):
        # Initialize variables to keep track of the nearest time and its time difference
        nearest_time = None
        min_time_difference = float("inf")

        for timestamp in predictions.keys():
            # Convert the timestamp string to a datetime object
            timestamp_dt = datetime.strptime(timestamp, "%Y/%m/%d %H:%M:%S")

            # Calculate the time difference
            time_difference = abs((timestamp_dt - target_time).total_seconds())

            # Check if this is the closest time found so far
            if time_difference < min_time_difference:
                min_time_difference = time_difference
                nearest_time = timestamp

        return nearest_time
    
    def create_historical_dataframe(self, aggregates):
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
    
    def adjust_score(self, x):
            if x > 1:
                return 1
            elif x < 0:
                return 0
            else:
                return x
            
    def calculate_anomaly_score(self, current_agg, past_data, preds):
        past_data.sort_values(by = ['area_id', 'ds'], ignore_index = True, inplace = True)
        mstd_24 = past_data.groupby('area_id')['y'].std().reset_index()['y']
        current_agg.rename(columns = {'poly_id': 'area_id'}, inplace = True)
        current_agg.sort_values(by = ['area_id'], ignore_index = True, inplace = True)
        current_agg['mstd_24'] = mstd_24
        preds['area_id'] = preds['area_id'].astype('int64')
        final = current_agg.merge(
            preds,
            how = 'inner',
            left_on = ['area_id'],
            right_on = ['area_id']
        )
        final['prophet_score'] = (
            (final['ebike_availibility'] - final['pred_upper']) * (final['ebike_availibility'] >= final['pred']) +
            (final['pred_lower'] - final['ebike_availibility']) * (final['ebike_availibility'] < final['pred'])
        )
        final['anomaly_score'] = ((final['prophet_score'] - final['mstd_24'])/ (2 * final['mstd_24'])) + 0.5
        
        final['anomaly_score'] = final['anomaly_score'].apply(
            lambda x: self.adjust_score(x)
        )
        final['anomaly'] = final['anomaly_score'].apply(
            lambda x: 1 if x > 0.5 else 0
        )
        return final
