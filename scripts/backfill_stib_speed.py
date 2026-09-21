"""Recompute STIB speed and aggregated speed over a period, in place.

The live harvesters only ever append rows newer than their latest one, so the
history they produced while misconfigured (see speed.py / aggregated_speed.py)
stays wrong until it is rewritten. This script walks the source table
chronologically and, for every snapshot in the period, recomputes the result
the way the harvester would today and writes it over the existing row: the
blob keeps its name (it is named after the date, so its URL does not change)
and the row keeps its date, only `data`, `hash` and `type` are updated. A
snapshot the old harvester skipped (one in two since 2026-03-30) gets a new
row. Nothing is deleted and the service keeps running: it never touches dates
older than its latest row, and `--end` is capped a few minutes in the past.

Run the speed phase before the aggregated one, since the latter reads the
former. Days are processed in parallel; every worker warms its window up with
the rows just before its day so day boundaries are seamless.

    python scripts/backfill_stib_speed.py --phase speed --start 2026-03-30 --workers 6
    python scripts/backfill_stib_speed.py --phase aggregated --start 2026-03-30 --workers 6

`--dry-run` computes but writes nothing, and prints what would change.
"""
import argparse
import hashlib
import json
import logging
import os
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from multiprocessing import get_context

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy import text  # noqa: E402

from components.stib.harvesters.aggregated_speed import WINDOW, aggregate  # noqa: E402
from components.stib.harvesters.speed import compute_speeds  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(processName)s %(message)s")
log = logging.getLogger("backfill")
logging.getLogger("azure").setLevel(logging.WARNING)

SOURCE_KEEP = 4  # snapshots kept behind the current one when looking for a distinct previous


def _engine():
    from src.data.engine import engine
    return engine


def _storage():
    from src.data.storage import storage_manager
    return storage_manager


def _rows(conn, table, start, end):
    """(date, url, hash) for the rows of `table` in [start, end), following copy_id like base_query."""
    return conn.execute(text(f"""
        select t.date, coalesce(t2.data, t.data), t.hash
        from {table} t left join {table} t2 on t.copy_id = t2.id
        where t.date >= :s and t.date < :e and (t.copy_id is not null or t.hash is not null)
        order by t.date asc
    """), {"s": start, "e": end}).fetchall()


def _existing(conn, table, start, end):
    return {r[0]: r[1] for r in conn.execute(text(
        f"select date, hash from {table} where date >= :s and date < :e"), {"s": start, "e": end}).fetchall()}


def _read_json(url):
    raw = _storage().read(url)
    return json.loads(raw) if raw else []


def _write(conn, table, date, result, existing, dry_run):
    """Write `result` for `date` into `table`; returns 'same' | 'updated' | 'inserted'."""
    data_bytes = None if result is None else json.dumps(result).encode("utf-8")
    digest = None if data_bytes is None else hashlib.md5(data_bytes).hexdigest()
    if date in existing:
        if existing[date] == digest:
            return "same"
        outcome = "updated"
    else:
        outcome = "inserted"
    if dry_run:
        return outcome
    url = _storage().write(f"{table}/{date.strftime('%Y-%m-%d_%H-%M-%S')}", data_bytes)
    if outcome == "updated":
        conn.execute(text(f"update {table} set data=:u, hash=:h, type='json', copy_id=null where date=:d"),
                     {"u": url, "h": digest, "d": date})
    else:
        conn.execute(text(f"insert into {table} (date, data, hash, type) values (:d, :u, :h, 'json')"),
                     {"d": date, "u": url, "h": digest})
    return outcome


def speed_day(args):
    start, end, dry_run = args
    counts = {"same": 0, "updated": 0, "inserted": 0}
    with _engine().connect() as conn:
        warmup = conn.execute(text("""
            select t.date, coalesce(t2.data, t.data) from stib_vehicle_distance t
            left join stib_vehicle_distance t2 on t.copy_id = t2.id
            where t.date < :s and (t.copy_id is not null or t.hash is not null)
            order by t.date desc limit :n"""), {"s": start, "n": SOURCE_KEEP}).fetchall()
        window = deque(maxlen=SOURCE_KEEP + 1)
        for date, url in reversed(warmup):
            window.append((date, _read_json(url)))
        existing = _existing(conn, "stib_speed", start, end)
        for date, url, _ in _rows(conn, "stib_vehicle_distance", start, end):
            current = _read_json(url)
            previous = next(((d, data) for d, data in reversed(window) if data != current), None)
            result = None if previous is None else compute_speeds(previous[1], previous[0], current, date)
            counts[_write(conn, "stib_speed", date, result, existing, dry_run)] += 1
            window.append((date, current))
        conn.commit()
    log.info("speed %s: %s", start.date(), counts)
    return counts


def aggregated_day(args):
    start, end, dry_run = args
    counts = {"same": 0, "updated": 0, "inserted": 0}
    with _engine().connect() as conn:
        window = deque()
        for date, url, _ in _rows(conn, "stib_speed", start - WINDOW, start):
            window.append((date, _read_json(url)))
        existing = _existing(conn, "stib_aggregated_speed", start, end)
        for date, url, _ in _rows(conn, "stib_speed", start, end):
            window.append((date, _read_json(url)))
            while window and window[0][0] < date - WINDOW:
                window.popleft()
            result = aggregate([data for _, data in window])
            counts[_write(conn, "stib_aggregated_speed", date, result, existing, dry_run)] += 1
        conn.commit()
    log.info("aggregated %s: %s", start.date(), counts)
    return counts


def _days(start, end):
    day = start
    while day < end:
        nxt = min(day + timedelta(days=1), end)
        yield day, nxt
        day = nxt


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase", choices=["speed", "aggregated"], required=True)
    p.add_argument("--start", required=True, help="naive UTC, e.g. 2026-03-30 or 2026-03-30T12:00")
    p.add_argument("--end", default=None, help="naive UTC, default: 10 minutes ago")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    start = datetime.fromisoformat(a.start)
    cap = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    end = min(datetime.fromisoformat(a.end), cap) if a.end else cap
    work = [(s, e, a.dry_run) for s, e in _days(start, end)]
    fn = speed_day if a.phase == "speed" else aggregated_day
    log.info("%s%s: %d day(s) from %s to %s with %d worker(s)",
             a.phase, " (dry run)" if a.dry_run else "", len(work), start, end, a.workers)

    total = {"same": 0, "updated": 0, "inserted": 0}
    with get_context("spawn").Pool(a.workers) as pool:
        for counts in pool.imap_unordered(fn, work):
            for k in total:
                total[k] += counts[k]
    log.info("done: %s", total)


if __name__ == "__main__":
    main()
