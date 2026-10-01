from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from src.components import Collector

BRUSSELS = ZoneInfo("Europe/Brussels")


class InfrabelPunctualityCollector(Collector):
    """Yesterday's departures (Brussels day), from Infrabel's "D-1" dataset.

    Infrabel replaces the dataset around 04:00 UTC. Collected at 01:30 UTC
    (until 2026-10-01), every file held the day before yesterday. A dataset not
    yet replaced is therefore refused, so the runner retries instead of storing
    the previous day a second time.
    """

    def run(self):
        data = requests.get(
            "https://opendata.infrabel.be/api/explore/v2.1/catalog/datasets/ruwe-gegevens-van-stiptheid-d-1/exports/json?lang=fr&timezone=Europe%2FBerlin"
        ).json()
        expected = expected_day()
        days = {row.get("datdep") for row in data}
        if days != {expected}:
            raise ValueError(f"Infrabel punctuality holds {sorted(map(str, days))}, not {expected} yet")
        return data


def expected_day(now: datetime = None) -> str:
    now = now or datetime.now(BRUSSELS)
    return (now.astimezone(BRUSSELS) - timedelta(days=1)).strftime("%Y-%m-%d")
