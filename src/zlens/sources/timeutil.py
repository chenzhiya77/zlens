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


def iso_to_epoch_ms(value: object) -> int | None:
    """ISO-8601 instant (e.g. '2026-09-01T23:45:39.061Z') → epoch ms.

    Qoder transcripts timestamp records with ISO strings while everything else
    in the app speaks epoch ms; malformed values degrade to None and the caller
    skips the record (no fabricated placement).
    """
    if not isinstance(value, str):
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None
