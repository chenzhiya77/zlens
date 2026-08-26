"""Epoch-millisecond helpers shared by source adapters.

Pure epoch arithmetic: Windows CRT localtime() raises OSError 22 for
timestamps near the epoch, so datetime.fromtimestamp() is unusable here.
"""

from datetime import UTC, datetime, timedelta

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)


def ms_to_datetime(ms: int | None) -> datetime | None:
    if ms is None:
        return None
    return (_EPOCH_UTC + timedelta(milliseconds=ms)).astimezone()


def ms_to_local_day(ms: int) -> str:
    return ms_to_datetime(ms).strftime("%Y-%m-%d")
