from motion_lake_client.client import ContentType

from src.configuration.model import ComponentConfiguration


def convert_local_data_type_to_motion_lake_data_type(component: ComponentConfiguration) -> ContentType:
    """
    Convert a local data type to a Motion Lake data type.
    :param data_type: The local data type
    :return: The Motion Lake data type
    """

    if component.data_format == "gtfs_realtime":
        return ContentType.GTFS_RT

    return {
        "json": ContentType.JSON,
        "bytes": ContentType.RAW,
        "binary": ContentType.RAW,
    }.get(component.data_type, ContentType.RAW)
