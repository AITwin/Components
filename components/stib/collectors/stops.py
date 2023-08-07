import json
from collections import defaultdict
from itertools import chain, product

import geopandas as gpd
import pandas as pd
import requests
import shapely
from bs4 import BeautifulSoup

from components.stib.utils.converter import convert_dataframe_column_stop_to_generic
from src.components import Collector


class STIBStopsCollector(Collector):
    def run(self):
        data = self.merge_unofficial_and_official_stops_data()

        with_lat_and_long = data[
            data["stop_lat"].notnull() & data["stop_lon"].notnull()
            ]

        response_gdf = gpd.GeoDataFrame(
            with_lat_and_long,
            crs="epsg:4326",
            geometry=[
                shapely.geometry.Point(xy)
                for xy in zip(
                    with_lat_and_long["stop_lon"], with_lat_and_long["stop_lat"]
                )
            ],
        )

        return json.loads(response_gdf.to_json())

    @staticmethod
    def merge_unofficial_and_official_stops_data():
        stops_per_line = pd.read_csv(
            "https://stibmivb.opendatasoft.com/explore/dataset/gtfs-files-production/files"
            "/7068c8d492df76c5125fac081b5e09e9/download/"
        )

        stops_per_line["stop_id"] = convert_dataframe_column_stop_to_generic(
            stops_per_line["stop_id"]
        )

        stops_per_line = stops_per_line[["stop_id", "stop_lat", "stop_lon"]]

        unofficial_stops_per_line = STIBStopsCollector.unofficial_fetch_stops_by_line()

        merged = unofficial_stops_per_line.merge(
            stops_per_line, on=["stop_id"], how="left"
        )

        # Drop duplicates
        merged = merged.drop_duplicates(
            subset=["stop_id", "route_short_name", "direction_id"], keep="first"
        )

        return merged

    @staticmethod
    def unofficial_fetch_stops_by_line():
        """
        Fetches the stops by line from the unofficial STIB API (web scraping).
        """
        stops_by_line = defaultdict(lambda: defaultdict(list))

        direction_choice = ("V", "F")

        noctis = [
            "N04",
            "N05",
            "N06",
            "N08",
            "N09",
            "N10",
            "N11",
            "N12",
            "N13",
            "N16",
            "N18",
        ]

        for line, direction in product(chain(range(1, 100), noctis), direction_choice):
            response = requests.get(
                f"https://www.stib-mivb.be/irj/servlet/prt/portal/prtroot/pcd!3aportal_content!2fSTIBMIVB!2fWebsite!2fFrontend!2fPublic!2fiViews!2fcom.stib.HorairesServletService?l=fr&_line={line}&_directioncode={direction}&_mode=rt"
            )

            # parse the HTML content of the response using Beautiful Soup
            soup = BeautifulSoup(response.content, "html.parser")

            # find all the li elements with class "thermometer__stop"
            li_elements = soup.find_all("li", class_="thermometer__stop")

            # extract the id and inner text of each li element
            for li in li_elements:
                stop_id = li.get("id")
                stop_text = li.text.replace("\n", "").strip()
                stops_by_line[line][direction].append(
                    {
                        "stop_id": stop_id,
                        "stop_name": stop_text,
                    }
                )

        data = []

        for line, directions in stops_by_line.items():
            for direction, stops in directions.items():
                for sequence, stop in enumerate(stops):
                    data.append(
                        {
                            "route_short_name": str(line).replace("T", ""),
                            "direction_id": direction,
                            "direction": 0 if direction == "V" else 1,
                            "stop_id": stop["stop_id"],
                            "stop_name": stop["stop_name"],
                            "stop_sequence": sequence,
                        }
                    )

        data_frame = pd.DataFrame(data)

        data_frame["stop_id"] = convert_dataframe_column_stop_to_generic(
            data_frame["stop_id"]
        )

        return data_frame
