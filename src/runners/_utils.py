from datetime import timedelta, datetime

import schedule


def schedule_string_to_function(schedule_string):
    """
    Convert a schedule string to a schedule.
    :param schedule_string: The schedule string
    :return: The schedule
    """

    # If ":" is in the schedule string, it is a time
    if ":" in schedule_string:
        return schedule.every().day.at(schedule_string)
    # Otherwise, if "s" is in the schedule string, it is a number of seconds
    elif "s" in schedule_string:
        return schedule.every(int(schedule_string.replace("s", ""))).seconds
    # Otherwise, if "m" is in the schedule string, it is a number of minutes
    elif "m" in schedule_string:
        return schedule.every(int(schedule_string.replace("m", ""))).minutes
    # Otherwise, if "h" is in the schedule string, it is a number of hours
    elif "h" in schedule_string:
        return schedule.every(int(schedule_string.replace("h", ""))).hours
    # Otherwise, if "d" is in the schedule string, it is a number of days
    elif "d" in schedule_string:
        return schedule.every(int(schedule_string.replace("d", ""))).days

    raise ValueError(f"Invalid schedule string: {schedule_string}")


def schedule_string_to_time_delta(schedule_string) -> timedelta:
    """
    Convert a schedule string to a time delta.
    :param schedule_string: The schedule string
    :return: The time delta
    """

    if "s" in schedule_string:
        return timedelta(seconds=int(schedule_string.replace("s", "")))
    # Otherwise, if "m" is in the schedule string, it is a number of minutes
    elif "m" in schedule_string:
        return timedelta(minutes=int(schedule_string.replace("m", "")))
    # Otherwise, if "h" is in the schedule string, it is a number of hours
    elif "h" in schedule_string:
        return timedelta(hours=int(schedule_string.replace("h", "")))
    # Otherwise, if "d" is in the schedule string, it is a number of days
    elif "d" in schedule_string:
        return timedelta(days=int(schedule_string.replace("d", "")))
    elif "w" in schedule_string:
        return timedelta(weeks=int(schedule_string.replace("w", "")))

    raise ValueError(f"Invalid schedule string: {schedule_string}")


def round_datetime_to_previous_delta(date: datetime, delta: timedelta) -> datetime:
    """
    Round a datetime to the previous delta.
    :param date: The datetime
    :param delta: The delta
    :return: The rounded datetime
    """
    return date - (date - date.min) % delta
