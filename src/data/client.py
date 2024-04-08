import os

from motion_lake_client import BaseClient

client = BaseClient(os.environ.get("MOTION_LAKE_URL", "http://localhost:8000"))
