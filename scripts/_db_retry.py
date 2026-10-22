"""Retry a unit of backfill work when the catalogue database drops the connection.

Azure restarts the Postgres server for maintenance now and then (2026-10-14 23:21
UTC killed a two-week backfill chain). The backfills only write rows that are
missing or different, so a unit of work can simply be run again once the server
is back.
"""
import logging
import time

from sqlalchemy.exc import OperationalError

log = logging.getLogger("backfill")

ATTEMPTS = 12
WAIT = 300  # seconds: 12 × 5 min outlasts a maintenance restart


def run_with_retry(engine, fn, *args):
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return fn(*args)
        except OperationalError as exc:
            if attempt == ATTEMPTS:
                raise
            log.warning("database unavailable (%s), retry %d/%d in %d s",
                        str(exc.orig).strip().splitlines()[0], attempt, ATTEMPTS - 1, WAIT)
            engine.dispose()
            time.sleep(WAIT)
