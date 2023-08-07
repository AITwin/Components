import os

import pysftp

from src.components import Collector


class DeLijnGTFSStaticCollector(Collector):
    def run(self):
        # Need to disable host key checking because the host key is not in the known hosts file
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None
        with pysftp.Connection(
            host="transfer.delijn.be",
            username=os.environ["DE_LIJN_SFTP_USERNAME"],
            password=os.environ["DE_LIJN_SFTP_PASSWORD"],
            cnopts=cnopts,
            default_path="/Public",
        ) as sftp:
            with sftp.open("gtfs_transit.zip") as f:
                return f.read()
