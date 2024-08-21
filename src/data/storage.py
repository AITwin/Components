import abc
import os

from azure.storage.blob import BlobServiceClient


class StorageManager(abc.ABC):
    @abc.abstractmethod
    def write(self, file_name: str, data: bytes): ...

    @abc.abstractmethod
    def read(self, file_name: str) -> bytes: ...


class AzureBlobManager(StorageManager):
    def __init__(self, connection_string, container_name):
        self.blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )
        self.container_client = self.blob_service_client.get_container_client(
            container_name
        )

    def write(self, file_name: str, data: bytes) -> str:
        """
        Write data to a blob in Azure Blob Storage.

        :param file_name: Name of the blob to create or update.
        :param data: Data to write to the blob. Can be a string or bytes.

        :return: URL of the blob.
        """
        blob_client = self.container_client.get_blob_client(file_name)
        blob_client.upload_blob(data, overwrite=True)

        return blob_client.url

    def read(self, file_name: str) -> bytes:
        """
        Read data from a blob in Azure Blob Storage.

        :param file_name: Name of the blob to read from.
        :return: Data read from the blob as bytes.
        """
        blob_client = self.container_client.get_blob_client(file_name)
        blob_data = blob_client.download_blob().readall()
        return blob_data


class FileStorageManager(StorageManager):
    def __init__(self, directory):
        self.directory = directory

    def write(self, file_name: str, data: bytes) -> str:
        """
        Write data to a file in the local file system.

        :param file_name: Name of the file to create or update.
        :param data: Data to write to the file. Can be a string or bytes.

        :return: Path of the file.
        """
        file_path = os.path.join(self.directory, file_name)
        # create directory if it does not exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "wb") as file:
            file.write(data)

        return file_path

    def read(self, file_name: str) -> bytes:
        """
        Read data from a file in the local file system.

        :param file_name: Name of the file to read from.
        :return: Data read from the file as bytes.
        """
        with open(file_name, "rb") as file:
            return file.read()


def lazy(func):
    return property(lambda self: func())


storage_manager = lazy(
    lambda: AzureBlobManager(
        os.environ["AZURE_STORAGE_CONNECTION_STRING"],
        os.environ["AZURE_STORAGE_CONTAINER"],
    )
)
