from io import BytesIO
from typing import Tuple
from zipfile import ZipFile


def extract_zip_content(zip_file: bytes) -> Tuple[str, str]:
    """
    Extracts the content of a zip file.
    :param zip_file:  The content of the zip file.
    :return:  A tuple containing the name and content of each file in the zip file.
    """ """
    """
    with ZipFile(BytesIO(zip_file)) as zip_file:
        for name in zip_file.namelist():
            content = zip_file.read(name).decode("utf-8")
            yield name, content


def zip_to_dict(zip_file: bytes) -> dict:
    """
    Converts a zip file to a dictionary.
    zip_file: The content of the zip file.
    return: A dictionary containing the content of the zip file.
    """
    output = {}

    for name, content in extract_zip_content(zip_file):
        output[name] = content

    return output
