"""Fill `stib_vehicle_trip` for the period before the live harvester started.

The live harvester (components/stib/harvesters/vehicle_trip) runs LATEST_ONLY,
so its history begins the day it was deployed. This script replays the
`vehicle_distance` archive through the same harvester class, poll by poll,
with the timetable and segments that were in force at each poll, and writes
the snapshots the way the runner does (blob named after the date, one row per
poll). Dates that already have a row are left alone, so it can be stopped and
restarted, and it never reaches the live rows (`--end` defaults to the first).

The period is cut into chunks of `--chunk-days`, processed in parallel, each by
one continuous tracker that first rebuilds from the hour before its chunk (the
harvester's own bootstrap). Chunk boundaries therefore behave like a restart of
the live service: identities are carried over from the previous snapshot where
it exists. Before `stib_segments` begins (2024-08-21) vehicles are drawn on
straight stop-to-stop lines. Polls that yield no vehicle write no row.

    python scripts/backfill_stib_vehicle_trip.py --start 2024-04-06 --workers 1
    python scripts/backfill_stib_vehicle_trip.py --start 2026-09-29T14:00 --end 2026-09-29T14:20 --dry-run

`--dry-run` computes but writes nothing, and saves the snapshots it would
write under `--dump` for inspection.
"""
import argparse
import bisect
import hashlib
import json
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime, timedelta
from multiprocessing import get_context

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy import text  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(processName)s %(message)s")
log = logging.getLogger("backfill")
logging.getLogger("azure").setLevel(logging.WARNING)

TABLE = "stib_vehicle_trip"
SOURCE = "stib_vehicle_distance"
HISTORY = 180          # polls kept for a rebuild, as OPTIONAL_DEPENDENCIES_LIMIT
BOOTSTRAP = timedelta(hours=1)


def _engine():
    from src.data.engine import engine
    return engine


def _storage():
    from src.data.storage import storage_manager
    return storage_manager


class _Row:
    """What the runner hands a harvester: a date and its (here, already read) data."""

    def __init__(self, date, data=None, url=None, data_type=None):
        self.date, self._data, self._url, self._type = date, data, url, data_type

    @property
    def data(self):
        if self._data is None and self._url is not None:
            raw = _storage().read(self._url)
            self._data = json.loads(raw) if self._type == "json" else raw
        return self._data


def _source(conn, start, end):
    """(date, url) of the polls in [start, end), following copy_id like base_query."""
    return conn.execute(text(f"""
        select t.date, coalesce(t2.data, t.data) from {SOURCE} t
        left join {SOURCE} t2 on t.copy_id = t2.id
        where t.date >= :s and t.date < :e and (t.copy_id is not null or t.hash is not null)
        order by t.date asc"""), {"s": start, "e": end}).fetchall()


def _versions(conn, table):
    """(dates, rows) of a slowly-changing dependency, to pick the one in force."""
    rows = conn.execute(text(f"""
        select t.date, coalesce(t2.data, t.data), t.type from {table} t
        left join {table} t2 on t.copy_id = t2.id
        where t.copy_id is not null or t.hash is not null order by t.date asc""")).fetchall()
    return [r[0] for r in rows], [_Row(r[0], url=r[1], data_type=r[2]) for r in rows]


def _in_force(versions, date):
    """The latest version strictly before `date`, as retrieve_latest_rows_before_datetime."""
    dates, rows = versions
    i = bisect.bisect_left(dates, date)
    return rows[i - 1] if i else None


def _write(conn, date, result):
    data_bytes = json.dumps(result).encode("utf-8")
    url = _storage().write(f"{TABLE}/{date.strftime('%Y-%m-%d_%H-%M-%S')}", data_bytes)
    conn.execute(text(f"insert into {TABLE} (date, data, hash, type) values (:d, :u, :h, 'json')"),
                 {"d": date, "u": url, "h": hashlib.md5(data_bytes).hexdigest()})


def chunk(args):
    start, end, dry_run, dump = args
    from components.stib.harvesters.vehicle_trip import STIBVehicleTripHarvester
    from components.stib.harvesters.vehicle_trip import harvester as module

    module._state.update(tracker=None, timetable=None)
    harvester = STIBVehicleTripHarvester()
    counts = {"written": 0, "existing": 0, "empty": 0}
    started = time.time()
    with _engine().connect() as conn:
        gtfs, segments = _versions(conn, "stib_gtfs_parquet"), _versions(conn, "stib_segments")
        existing = {r[0] for r in conn.execute(
            text(f"select date from {TABLE} where date >= :s and date < :e"), {"s": start, "e": end})}
        # The hour before the chunk, for the tracker's first rebuild; newest last.
        history = deque((_Row(d, url=u, data_type="json") for d, u in _source(conn, start - BOOTSTRAP, start)),
                        maxlen=HISTORY)
        previous = None
        polls = _source(conn, start, end)
        for n, (date, url) in enumerate(polls):
            source = _Row(date, url=url, data_type="json")
            timetable = _in_force(gtfs, date)
            if date in existing or timetable is None:
                counts["existing" if date in existing else "empty"] += 1
                history.append(source)
                continue
            result = harvester.run(source, timetable, _in_force(segments, date),
                                   list(reversed(history)), previous)
            history.append(source)
            if result is None:
                counts["empty"] += 1
                continue
            previous = _Row(date, data=result)
            if dry_run:
                if dump:
                    with open(os.path.join(dump, date.strftime("%Y-%m-%d_%H-%M-%S")), "w") as f:
                        json.dump(result, f)
            else:
                _write(conn, date, result)
                if n % 100 == 0:
                    conn.commit()
            counts["written"] += 1
        conn.commit()
    log.info("%s -> %s: %s in %.0f s", start, end, counts, time.time() - started)
    return counts


def _chunks(start, end, days):
    at = start
    while at < end:
        nxt = min(at + timedelta(days=days), end)
        yield at, nxt
        at = nxt


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", default="2024-04-05T04:21", help="naive UTC; the timetable archive begins 2024-04-05 04:20")
    p.add_argument("--end", default=None, help="naive UTC, default: the first live row")
    p.add_argument("--chunk-days", type=float, default=7)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--newest-first", action="store_true", help="recent history becomes available first")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dump", default=None, help="with --dry-run, a directory for the snapshots")
    a = p.parse_args()

    start = datetime.fromisoformat(a.start)
    if a.end:
        end = datetime.fromisoformat(a.end)
    else:
        with _engine().connect() as conn:
            end = conn.execute(text(f"select min(date) from {TABLE}")).scalar() or datetime.utcnow()
    if a.dump:
        os.makedirs(a.dump, exist_ok=True)
    work = [(s, e, a.dry_run, a.dump) for s, e in _chunks(start, end, a.chunk_days)]
    if a.newest_first:
        work.reverse()
    log.info("%s%d chunk(s) from %s to %s with %d worker(s)",
             "(dry run) " if a.dry_run else "", len(work), start, end, a.workers)
    total = {"written": 0, "existing": 0, "empty": 0}
    with get_context("spawn").Pool(a.workers) as pool:
        for counts in pool.imap_unordered(chunk, work):
            for k in total:
                total[k] += counts[k]
            log.info("progress: %s", total)
    log.info("done: %s", total)


if __name__ == "__main__":
    main()
