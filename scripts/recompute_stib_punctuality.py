"""Recompute stored `stib_punctuality` days in place after a change to the reconstruction.

The runner only moves forward, so a fix to the pipeline (e.g. tracking metro
trains per direction, df6e10f) reaches past days only through this script. Each
stored day is rebuilt from the same inputs the runner gave it: the Brussels
calendar day of `vehicle_distance` polls ending at the row's date (the runner
files a `1d@Europe/Brussels` period under its end), and the timetable in force
strictly before that date. The result overwrites the day's blob under the same
name and the row's hash is updated, so the endpoint keeps serving every day
throughout. Rows without data (days with no polls) are left alone.

    python scripts/recompute_stib_punctuality.py --start 2024-04-05 --workers 1
    python scripts/recompute_stib_punctuality.py --start 2026-09-29 --end 2026-09-30 --dry-run

Days already recomputed are listed in `--done` (one row date per line), so the
script can be stopped and restarted.
"""
import argparse
import hashlib
import io
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from multiprocessing import get_context
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy import text  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(processName)s %(message)s")
log = logging.getLogger("recompute")
logging.getLogger("azure").setLevel(logging.WARNING)

TABLE = "stib_punctuality"
SOURCE = "stib_vehicle_distance"
GTFS = "stib_gtfs_parquet"
BRUSSELS = ZoneInfo("Europe/Brussels")
UTC = ZoneInfo("UTC")


def _engine():
    from src.data.engine import engine
    return engine


def _storage():
    from src.data.storage import storage_manager
    return storage_manager


class _Row:
    def __init__(self, date, data):
        self.date, self.data = date, data


def _period(end):
    """[start, end) of the Brussels day the runner filed under `end` (naive UTC)."""
    local_end = end.replace(tzinfo=UTC).astimezone(BRUSSELS)
    local_start = (local_end - timedelta(hours=12)).replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(UTC).replace(tzinfo=None), end


def _read_json(url):
    raw = _storage().read(url)
    return json.loads(raw) if raw else None


def day(args):
    row_id, end, url, dry_run = args
    from components.stib.harvesters.punctuality import STIBPunctualityHarvester

    started = time.time()
    start, end = _period(end)
    with _engine().connect() as conn:
        # As retrieve_between_datetime: strictly inside the period, copies followed.
        polls = conn.execute(text(f"""
            select t.date, coalesce(t2.data, t.data) from {SOURCE} t
            left join {SOURCE} t2 on t.copy_id = t2.id
            where t.date > :s and t.date < :e and (t.copy_id is not null or t.hash is not null)
            order by t.date asc"""), {"s": start, "e": end}).fetchall()
        gtfs = conn.execute(text(f"""
            select coalesce(t2.data, t.data) from {GTFS} t
            left join {GTFS} t2 on t.copy_id = t2.id
            where t.date < :e and (t.copy_id is not null or t.hash is not null)
            order by t.date desc limit 1"""), {"e": end}).scalar()
    with ThreadPoolExecutor(16) as pool:
        payloads = list(pool.map(_read_json, [u for _, u in polls]))
    source = [_Row(d, p) for (d, _), p in zip(polls, payloads)]
    timetable = _Row(None, _storage().read(gtfs))

    result = STIBPunctualityHarvester().run(source, timetable)
    if result is None:
        log.warning("%s: no result, row left as is", end)
        return end, None
    if not dry_run:
        name = f"{TABLE}/{end.strftime('%Y-%m-%d_%H-%M-%S')}"
        new_url = _storage().write(name, result)
        with _engine().begin() as conn:
            conn.execute(text(f"update {TABLE} set data = :u, hash = :h where id = :i"),
                         {"u": new_url, "h": hashlib.md5(result).hexdigest(), "i": row_id})
    log.info("%s: %d polls, %.0f KB, %.0f s%s", end, len(polls), len(result) / 1024,
             time.time() - started, " (dry run)" if dry_run else "")
    return end, len(result)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", default="2024-04-05", help="first row date to recompute (naive UTC)")
    p.add_argument("--end", default=None, help="row dates strictly before this (naive UTC), default all")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--done", default="recompute_stib_punctuality.done")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    done = set()
    if os.path.exists(a.done):
        done = {line.strip() for line in open(a.done) if line.strip()}
    with _engine().connect() as conn:
        rows = conn.execute(text(f"""
            select id, date, data from {TABLE}
            where date >= :s and date < :e and hash is not null and copy_id is null
            order by date asc"""),
            {"s": datetime.fromisoformat(a.start),
             "e": datetime.fromisoformat(a.end) if a.end else datetime.max}).fetchall()
    work = [(r[0], r[1], r[2], a.dry_run) for r in rows if r[1].isoformat() not in done]
    log.info("%s%d day(s) to recompute (%d already done) with %d worker(s)",
             "(dry run) " if a.dry_run else "", len(work), len(rows) - len(work), a.workers)
    with get_context("spawn").Pool(a.workers, maxtasksperchild=1) as pool:
        for end, size in pool.imap_unordered(day, work):
            if size is not None and not a.dry_run:
                with open(a.done, "a") as f:
                    f.write(end.isoformat() + "\n")
    log.info("done")


if __name__ == "__main__":
    main()
