import pandas as pd


def convert_gtfs_line_to_num(gtfs_line: str) -> int:
    if "N" in gtfs_line:
        gtfs_line = "2" + gtfs_line[1:]

    return int(gtfs_line.lstrip("0").replace("B", "").replace("M", "").replace("T", ""))


def convert_line_to_generic(line: str) -> str:
    line = line.lstrip("0").replace("B", "").replace("M", "").replace("T", "")
    line = line.replace("b", "").replace("m", "").replace("t", "")

    return line


def convert_dataframe_column_stop_to_generic(series: pd.Series):
    return series.str.replace("[FGHCBP]", "", regex=True).astype(int)




def convert_shapefile_line_to_num(shapefile_line: str) -> int:
    return int(
        shapefile_line.lstrip("0").replace("b", "").replace("m", "").replace("t", "")
    )


def convert_shapefile_line_to_stops_line(shapefile_line: str):
    if shapefile_line[0] == "2":
        shapefile_line = "N" + shapefile_line[1:]

    return shapefile_line.lstrip("0").replace("b", "").replace("m", "").replace("t", "")


def convert_stib_strange_time_to_timestamp(time_str, starting_timestamp) -> int:
    """
    Convert a time string in the format "hh:mm:ss" to a timestamp. The time string can actually be
    greater than 24 hours, in which case the timestamp will be the next day.
    @param starting_timestamp:  The timestamp of the day to which the time_str belongs
    @param time_str:          The time string to convert
    @return:                The timestamp corresponding to the time_str
    """
    local_timestamp: int = 0
    hour, minute, second = [int(time_str_part) for time_str_part in time_str.split(":")]

    if hour >= 24:
        hour -= 24
        local_timestamp += 24 * 60 * 60

    # Convert hour:min:sec to local_timestamp
    local_timestamp += hour * 60 * 60 + minute * 60 + second

    return starting_timestamp + local_timestamp
