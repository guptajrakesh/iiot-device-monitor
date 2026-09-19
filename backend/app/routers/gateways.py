from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import DeviceInstance

router = APIRouter(prefix="/api/gateways", tags=["gateways"])


@router.get("/{gateway_id}/config")
def gateway_config(gateway_id: str, session: Session = Depends(get_session)):
    """What an edge gateway polls to learn which devices/tags it owns.

    This is the mechanism that makes onboarding through the API/UI take
    effect without redeploying the gateway - it just picks up new rows here
    on its next poll.
    """
    instances = (
        session.query(DeviceInstance)
        .filter_by(gateway_id=gateway_id, status="active")
        .all()
    )
    devices = [
        {
            "device_id": inst.id,
            "name": inst.name,
            "protocol": inst.protocol,
            "connection_config": inst.connection_config,
            "poll_interval_seconds": inst.poll_interval_seconds,
            "tags": [
                {"tag_key": t.tag_key, "protocol_config": t.protocol_config, "scale": t.scale}
                for t in inst.tags
                if t.enabled
            ],
        }
        for inst in instances
    ]
    return {"gateway_id": gateway_id, "devices": devices}
