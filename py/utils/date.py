# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import calendar
import datetime
import os
from typing import overload

import dateutil.parser
import numpy as np
import pytz
from django.utils import timezone

defaultTimezoneTimezone: str | None = None


# Returns current season as string: 'summer', 'spring', 'fall' or 'winger'
# Uses input month if available
def getCurSeason(month=None):
    month = timezone.now().month if month is None else month
    if 3 <= month <= 5:
        return 'spring'
    if 6 <= month <= 8:
        return 'summer'
    if 9 <= month <= 11:
        return 'fall'
    if month <= 2 or month >= 12:
        return 'winter'

    raise Exception('unknown month')


def getSeasonMonths(season):
    if season == 'spring':
        return (3, 4, 5)
    if season == 'summer':
        return (6, 7, 8)
    if season == 'fall':
        return (9, 10, 11)
    if season == 'winter':
        return (12, 1, 2)

    raise Exception(f"invalid season: `{season}`")


def getYearSeasonDates(year: int, season: str) -> tuple[datetime.datetime, datetime.datetime]:
    months = getSeasonMonths(season)
    startDate = datetime.datetime(year, months[0], 1, 0, 0, 0, 0)

    endYear = year if season != 'winter' else year + 1
    endMonthDays = calendar.monthrange(endYear, months[-1])[1]
    endDate = datetime.datetime(endYear, months[-1], endMonthDays, 23, 59, 59, 999)

    return startDate, endDate


def getMonthCode(date: datetime.datetime) -> str:
    """Two-letter code for month"""
    return {
        1: 'JN',
        2: 'FB',
        3: 'MR',
        4: 'AP',
        5: 'MY',
        6: 'JN',
        7: 'JL',
        8: 'AG',
        9: 'SP',
        10: 'OC',
        11: 'NV',
        12: 'DC',
    }[date.month]


def getDefaultTimezone() -> str:
    global defaultTimezoneTimezone  # pylint: disable=global-statement

    if defaultTimezoneTimezone is None:
        defaultTimezoneTimezone = timezone.get_default_timezone_name()  # Getting default timezone is expensive

    return defaultTimezoneTimezone


@overload
def defaultTimezone(dt: datetime.datetime) -> datetime.datetime: ...


@overload
def defaultTimezone(dt: None) -> None: ...


def defaultTimezone(dt: datetime.datetime | None) -> datetime.datetime | None:
    """Add timezone info to datetime. Does not change the date/time itself"""
    if dt is None:
        return None

    return pytz.timezone(getDefaultTimezone()).localize(dt)


localTimezone = defaultTimezone


# Adds UTC timezone to datetime
def utcTimezone(dt: datetime.datetime) -> datetime.datetime:
    """Sets timezone. Does not mess with the time"""
    return pytz.utc.localize(dt)


def toLocalTimezone(dt: datetime.datetime) -> datetime.datetime:
    """Changes time to match target timezone"""
    # logging.info('++++ default timezone: {}'.format(timezone.get_default_timezone_name()))
    return dt.astimezone(pytz.timezone(timezone.get_default_timezone_name()))


def toUtcTimezone(dt: datetime.datetime) -> datetime.datetime:
    """Changes time to match target timezone"""
    return dt.astimezone(pytz.utc)


def toGmtTimezone(dt: datetime.datetime) -> datetime.datetime:
    """Changes time to match target timezone"""
    return dt.astimezone(pytz.timezone('GMT'))


def utcDateFromStr(s: str, changeTime: bool = False) -> datetime.datetime:
    if ':' in s:
        dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datetime.datetime.strptime(s, '%Y-%m-%d')
    if changeTime:
        # Change time to timezone, assuming local timezone in source string
        return toUtcTimezone(dt)
    # Just apply timezone label
    return utcTimezone(dt)


def localDateFromStr(s: str, changeTime: bool = False) -> datetime.datetime:
    if ':' in s:
        try:
            dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M')
    else:
        dt = datetime.datetime.strptime(s, '%Y-%m-%d')
    if changeTime:
        # Change time to timezone, assuming local timezone in source string
        return toLocalTimezone(dt)
    # Just apply timezone label
    return defaultTimezone(dt)


def toLocalRemoveTz(dt: datetime.datetime) -> datetime.datetime:
    """Moves datetime to local time and removes timezone"""
    return dt.astimezone(pytz.timezone(timezone.get_default_timezone_name())).replace(tzinfo=None)


# Increment month value of datetime and return new datetime. Day, hour, etc are cleared
def incrMonth(dt: datetime.date, incr: int) -> datetime.datetime:
    month = dt.month + incr

    return defaultTimezone(
        datetime.datetime(
            year=dt.year + (month - 1) // 12,
            month=(month - 1) % 12 + 1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )


def incrDateMonth(dt: datetime.date, incr: int) -> datetime.date:
    month = dt.month + incr
    return datetime.date(year=dt.year + (month - 1) // 12, month=(month - 1) % 12 + 1, day=1)


def incrMonthNoTz(dt: datetime.datetime, incr: int) -> datetime.datetime:
    month = dt.month + incr

    return datetime.datetime(
        year=dt.year + (month - 1) // 12,
        month=(month - 1) % 12 + 1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def incrMonthKeep(dt: datetime.datetime, incr: int) -> datetime.datetime:
    """Increment month. Keep all other data, but cap date if it gets too far out"""
    month = dt.month + incr
    newMonth = (month - 1) % 12 + 1
    newYear = dt.year + (month - 1) // 12
    lastDayOfMonth = calendar.monthrange(newYear, newMonth)[1]

    if isinstance(dt, datetime.datetime):
        return datetime.datetime(
            year=newYear,
            month=newMonth,
            day=min(dt.day, lastDayOfMonth),
            hour=dt.hour,
            minute=dt.minute,
            second=dt.second,
            microsecond=dt.microsecond,
            tzinfo=dt.tzinfo,
        )

    return datetime.date(year=newYear, month=newMonth, day=min(dt.day, lastDayOfMonth))


def fileModifiedTime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


# Returns expected ship date for an order created at the given time.
# Returns tuple containing (expectedShipDate, certain), where certain is False if we are not certain we will meet the date
def getOrderExpectedShipDate(orderCreatedDate: datetime.datetime) -> tuple[datetime.datetime, bool]:
    if orderCreatedDate.day > 25 or orderCreatedDate.day < 7:
        # May be able to ship this order ahead of time. Not certain
        return (
            (incrMonth(orderCreatedDate, 1) if orderCreatedDate.day > 15 else orderCreatedDate).replace(
                day=8, hour=14, minute=0, second=0, microsecond=0
            ),
            False,
        )
    # Regular date-span. Guaranteed to ship next month
    return (incrMonth(orderCreatedDate, 1).replace(day=1, hour=14), True)


def getNextMajorShipDate(date: datetime.datetime) -> datetime.datetime:
    return incrMonth(date, 1).replace(day=1, hour=14)  # First of next month, always


# #Cluster dates by distance (in seconds), and return tuples of start- and end-dates covering the given input dates
# #returns: [(begin, end, [indices]), ...]
# def clusterDates(dates, threshold):
#     if not dates:
#         return []
#     elif len(dates) == 1:
#         return [(dates[0], dates[0], [0])]

#     #Get timestamps
#     times = np.array([d.timestamp() for d in dates])
#     #Cluster by timestamps
#     res = fclusterdata(times.reshape((len(times), 1)), threshold, criterion='distance', method='complete', metric='euclidean')

#     #Group clusters
#     clusters = defaultdict(list)
#     for itemI, groupI in enumerate(res):
#         clusters[groupI].append(itemI)


#     #Compose result
#     ret = [(datetime.datetime.fromtimestamp(min(times[i] for i in items)),
#              datetime.datetime.fromtimestamp(max(times[i] for i in items)),
#              items,
#              ) for groupI, items in clusters.items()]

#     #Sort result by start data
#     ret.sort(key=lambda v: v[0])

#     return ret


# Cluster dates by consecutive range (in seconds), and return tuples of start- and end-dates covering the given input dates
# Dates will be shuffled to make proper groups
# returns: [(begin, end, indiceCount), ...]
def clusterDates(
    dates: list[datetime.datetime], threshold: int
) -> list[tuple[datetime.datetime, datetime.datetime, int]]:
    if not dates:
        return []
    if len(dates) == 1:
        return [(dates[0], dates[0], 0)]

    # Get timestamps
    times = np.array(sorted([d.timestamp() for d in dates]))

    start = None
    consecutive = 0  # Number of consecutive orders within range of eachother
    total = len(times)
    ret = []
    for i in range(1, total):
        within = times[i] - times[i - 1] <= threshold
        if within:
            consecutive += 1

        if start is None:
            if consecutive > 0:
                # Found start
                start = times[i - 1]
            else:
                # Previous item not part of any group
                ret.append(
                    (
                        datetime.datetime.fromtimestamp(times[i - 1]),
                        datetime.datetime.fromtimestamp(times[i - 1]),
                        1,
                    )
                )
        elif not within:
            # Found end
            ret.append(
                (
                    datetime.datetime.fromtimestamp(start),
                    datetime.datetime.fromtimestamp(times[i - 1]),
                    consecutive + 1,
                )
            )
            consecutive = 0
            start = None

    # Add last item if not part of group
    if len(dates) >= 2 and times[-1] - times[-2] > threshold:
        ret.append(
            (
                datetime.datetime.fromtimestamp(times[-1]),
                datetime.datetime.fromtimestamp(times[-1]),
                1,
            )
        )
    # Add any unfinished sequence
    elif start is not None and consecutive > 0:
        ret.append(
            (
                datetime.datetime.fromtimestamp(start),
                datetime.datetime.fromtimestamp(times[-1]),
                consecutive + 1,
            )
        )

    return ret


def tsRangeToText(startDate: float | None = None, endDate: float | None = None) -> str:
    """
    Convert date range to text
    if only startDate: 'after {startDate}'
    if only startDate: 'before {endDate}'
    else               'between {startDate} and {endDate}'
    """

    if startDate:
        startF = datetime.datetime.fromtimestamp(startDate).strftime('%Y-%m-%d %H:%M:%S')
    if endDate:
        endF = datetime.datetime.fromtimestamp(endDate).strftime('%Y-%m-%d %H:%M:%S')

    if startDate and endDate:
        return f"between {startF} and {endF}"  # pylint: disable=possibly-used-before-assignment
    if startDate:
        return f"after {startF}"
    if endDate:
        return f"before {endF}"
    return 'at any time'


def secondsToNamedPeriod(secondsOrTimedelta: float | datetime.timedelta, roundTo: int = 1) -> str:
    """Converts seconds to a string ending in 's', 'm', 'h' or 'd' depending on timespan"""
    if not isinstance(secondsOrTimedelta, (int, float)):
        seconds = secondsOrTimedelta.total_seconds()
    else:
        seconds = secondsOrTimedelta

    absSecs = abs(seconds)
    if absSecs < 2:
        return f"{round(seconds*1000, roundTo)} ms"
    if absSecs < 2 * 60:
        return f"{round(seconds, roundTo)} s"
    if absSecs < 2 * 3600:
        return f"{round(seconds/60, roundTo)} m"
    if absSecs < 2 * 3600 * 24:
        return f"{round(seconds/3600, roundTo)} h"

    return f"{round(seconds/(3600*24), roundTo)} d"


def parseShopifyDateStr(val: str) -> datetime.datetime | None:
    """Parses a shopify date string and returns a timezone-enabled datetime. Shopify timezone is CST (configured in Admin API)"""
    dval = dateutil.parser.parse(val)
    if dval.tzinfo is None or dval.tzinfo.utcoffset(dval) is None:  # If not timezone aware.. add it
        dval = defaultTimezone(dval)

    return dval


@overload
def genShopifyDateStr(val: None) -> None: ...


@overload
def genShopifyDateStr(val: datetime.datetime) -> str: ...


def genShopifyDateStr(val: datetime.datetime | None) -> str | None:
    """Generates a shopify date-string from value"""
    if val is None:
        return None

    sval = val.strftime('%Y-%m-%dT%H:%M:%S')

    # Shopify wants timezone in HH:MM format
    tz = val.strftime('%z')

    return f"{sval}{tz[0:2]}:{tz[2:4]}"


parseContentfulDateStr = parseShopifyDateStr
genContentfulDateStr = genShopifyDateStr


def parseBoldDateTimeStr(val: str) -> datetime.datetime | None:
    """Bold time is in UTC"""

    # Bold will sometimes throw us dates 0000-00-00. We store these as 'no date' aka None
    if val.startswith('0000-00-00'):
        return None

    dval = dateutil.parser.parse(val)
    if dval.tzinfo is None or dval.tzinfo.utcoffset(dval) is None:  # If not timezone aware.. add it
        dval = utcTimezone(dval)

    return dval


def genBoldDateTimeStr(val: datetime.datetime | datetime.date | None) -> str | None:
    """Generates a shopify date-string from value"""
    if val is None:
        return None

    if isinstance(val, datetime.datetime):
        return toUtcTimezone(val).strftime('%Y-%m-%d %H:%M:%S')

    return val.strftime('%Y-%m-%d')
