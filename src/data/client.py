import os

from .clientsrc import BaseClient


client = BaseClient(os.environ.get("MOTION_LAKE_URL", "http://localhost:8000"))
