STIB_OPEN_DATA_URL = "https://data.stib-mivb.brussels/api/v2"
STIB_OPEN_DATA_URL_DATASET = f"{STIB_OPEN_DATA_URL}/catalog/datasets"

VEHICLE_POSITION_DATASET = "vehicle-position-rt-production"

METRO = [
    1,
    2,
    5,
    6,
]
TRAM = [3, 4, 7, 8, 9, 19, 25, 39, 44, 51, 55, 62, 81, 82, 92, 93, 97]

METRO_AND_TRAM_LINES = [
    *METRO,
    *TRAM,
]

SPEED_LIMITS = {i: 50 for i in METRO}

SPEED_LIMITS.update({j: 30 for j in TRAM})

SPEED_LIMITS.update({12: 100})


def get_vehicle_speed_limit(line_id: int) -> int:
    return SPEED_LIMITS.get(line_id, 50)
