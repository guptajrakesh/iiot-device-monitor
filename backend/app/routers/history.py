from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_session

router = APIRouter(prefix="/api/readings", tags=["readings"])

# range -> (lookback window, bucket width) - both valid Postgres interval literals.
# Bucket width grows with the window so a 7-day chart isn't 10,000 raw points.
RANGE_CONFIG = {
    "1h": ("1 hour", "1 minute"),
    "6h": ("6 hours", "5 minutes"),
    "24h": ("24 hours", "15 minutes"),
    "7d": ("7 days", "2 hours"),
}


@router.get("/history")
def reading_history(
    device_instance_id: str,
    tag_key: str,
    range: str = "1h",
    session: Session = Depends(get_session),
):
    """Downsampled history for one device/tag, using TimescaleDB's time_bucket -
    this is what the live sparklines (in-browser only, reset on page reload)
    can't show: what a value did over the last hour/day/week."""
    if range not in RANGE_CONFIG:
        raise HTTPException(400, f"Unknown range '{range}'; expected one of {list(RANGE_CONFIG)}")
    lookback, bucket = RANGE_CONFIG[range]

    # Note: SQLAlchemy's text() treats a bind param immediately followed by "::"
    # as an unrecognized token (it reads "::" as a Postgres-cast escape and
    # backs off parameter detection), so CAST(...) is used instead of :name::type.
    rows = session.execute(
        text(
            "SELECT time_bucket(CAST(:bucket AS interval), time) AS bucket, avg(value) AS value "
            "FROM readings "
            "WHERE device_instance_id = :device_id AND tag_key = :tag_key "
            "AND time > now() - CAST(:lookback AS interval) "
            "GROUP BY bucket ORDER BY bucket"
        ),
        {"bucket": bucket, "device_id": device_instance_id, "tag_key": tag_key, "lookback": lookback},
    ).fetchall()
    return [{"time": r.bucket.isoformat(), "value": r.value} for r in rows]
