from datetime import datetime
from typing import Dict

import pandas as pd
from geopandas import GeoDataFrame
from sqlalchemy import Table

from src.data.retrieve import retrieve_between_datetime


def gdf_to_mf_json(
    gdf: GeoDataFrame,
    traj_id_property: str,
    datetime_column: str,
    temporal_properties: list = None,
    temporal_properties_static_fields: Dict[str, Dict] = None,
    interpolation: str = None,
    crs=None,
    trs=None,
) -> dict:
    """
    Converts a GeoDataFrame to a dictionary compatible with the Moving Features JSON (MF-JSON) specification.

    Args:
        gdf (GeoDataFrame): The input GeoDataFrame to convert.
        traj_id_property (str): The name of the column in the GeoDataFrame that represents the trajectory identifier.
        datetime_column (str): The name of the column in the GeoDataFrame that represents the datetime information.
        temporal_properties (list, optional): A list of column names in the GeoDataFrame that represent additional temporal properties.
                                               Defaults to None.
        temporal_properties_static_fields (Dict[str, Dict], optional): A dictionary mapping column names to static fields associated with the
                                                                      corresponding temporal property. One such static field is the unit of measurement (uom). Defaults to None.
        interpolation (str, optional): The interpolation method used for the temporal geometry. Defaults to None.
        crs (optional): Coordinate reference system for the MF-JSON. Defaults to None.
        trs (optional): Temporal reference system for the MF-JSON. Defaults to None.
    Returns:
        dict: The MF-JSON representation of the GeoDataFrame.
    """

    if not isinstance(gdf, GeoDataFrame):
        raise ValueError(
            "Not a GeoDataFrame, but a {} was supplied. This function only works with GeoDataFrames.".format(
                type(gdf)
            )
        )

    if not temporal_properties:
        temporal_properties = []

    rows = []

    for identifier, row in gdf.groupby(traj_id_property):
        datetimes = row[datetime_column].tolist()
        trajectory_data = {
            "type": "Feature",
            "properties": {
                traj_id_property: identifier,
                **row.drop(
                    columns=[
                        "geometry",
                        datetime_column,
                        traj_id_property,
                        *temporal_properties,
                    ]
                ).to_dict(orient="records")[0],
            },
            "temporalGeometry": {
                "type": "MovingPoint",
                "coordinates": list(zip(row.geometry.x, row.geometry.y)),
                "datetimes": datetimes,
            },
        }

        if interpolation:
            trajectory_data["temporalGeometry"]["interpolation"] = interpolation

        if crs:
            trajectory_data["crs"] = crs

        if trs:
            trajectory_data["trs"] = trs

        if temporal_properties:
            temporal_properties_data = _encode_temporal_properties(
                datetimes, row, temporal_properties, temporal_properties_static_fields
            )

            trajectory_data["temporalProperties"] = [temporal_properties_data]

        # Appending each trajectory data to the list of rows
        rows.append(trajectory_data)

    return {"type": "FeatureCollection", "features": rows}


def _encode_temporal_properties(
    datetimes, row, temporal_properties, temporal_properties_static_fields
):
    temporal_properties_data = {
        "datetimes": datetimes,
    }
    for prop in temporal_properties:
        temporal_properties_data[prop] = {
            "values": row[prop].tolist(),
        }
        if prop in (temporal_properties_static_fields or {}):
            temporal_properties_data[prop].update(
                temporal_properties_static_fields[prop]
            )
    return temporal_properties_data


def fetch_geojsons_and_return_mf_json(
    table: Table,
    id_column: str,
    start_timestamp: int = None,
    end_timestamp: int = None,
    columns_to_drop: list = None,
):
    if end_timestamp is None and start_timestamp is not None:
        end_timestamp = start_timestamp + 60 * 60
    elif start_timestamp is None and end_timestamp is not None:
        start_timestamp = end_timestamp - 60 * 60
    else:
        start_timestamp = datetime.utcnow().timestamp() - 60 * 60
        end_timestamp = datetime.utcnow().timestamp()

    datas = retrieve_between_datetime(
        table,
        datetime.utcfromtimestamp(start_timestamp),
        datetime.utcfromtimestamp(end_timestamp),
        limit=1000,
    )

    if not datas:
        return

    df = GeoDataFrame()

    for item in datas:
        gdf_for_one_time = GeoDataFrame.from_features(item.data["features"])
        gdf_for_one_time["timestamp"] = int(item.date.timestamp())
        df = pd.concat([df, gdf_for_one_time])

    if columns_to_drop:
        df.drop(columns=columns_to_drop, inplace=True)

    # Drop where only one row for id_column
    df = df.groupby(id_column).filter(lambda x: len(x) > 1)
    df = df.reset_index(drop=True)

    if len(df) == 0:
        return {
            "features": [],
            "type": "FeatureCollection",
        }

    return gdf_to_mf_json(df, id_column, "timestamp")
