#!/usr/bin/env python3
"""Which services run on a given date.

Operators disagree about how to say it. SNCB and De Lijn list every running date
as an exception and leave `calendar.txt` inert; TEC uses the weekly pattern and
only lists removals. Reading one and not the other silently yields a day with
almost no vehicles on it, so both are honoured.
"""
from datetime import date

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def as_date(value):
    if isinstance(value, date):
        return value
    text = str(value)
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def services_on(calendar, calendar_dates, target: date):
    """The set of service_ids running on `target`."""
    running = set()

    if calendar is not None and len(calendar):
        weekday = WEEKDAYS[target.weekday()]
        if weekday in calendar.columns:
            for row in calendar.itertuples():
                if not getattr(row, weekday):
                    continue
                if as_date(row.start_date) <= target <= as_date(row.end_date):
                    running.add(row.service_id)

    if calendar_dates is not None and len(calendar_dates):
        for row in calendar_dates.itertuples():
            if as_date(row.date) != target:
                continue
            if row.exception_type == 1:
                running.add(row.service_id)
            elif row.exception_type == 2:
                running.discard(row.service_id)

    return running
