import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import DeviceInstance, DeviceInstanceTag, DeviceTemplate
from ..mqtt_test import request_test_connection
from ..schemas import DeviceInstanceDetailOut, DeviceInstanceIn, DeviceInstanceOut, TestConnectionRequest

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _tags_from_template(session: Session, template_id: str | None) -> list[DeviceInstanceTag]:
    if not template_id:
        return []
    template = session.get(DeviceTemplate, template_id)
    if not template:
        raise HTTPException(400, "Unknown template_id")
    return [
        DeviceInstanceTag(
            tag_key=t.tag_key, display_name=t.display_name, data_type=t.data_type,
            unit=t.unit, scale=t.scale, protocol_config=t.protocol_config,
        )
        for t in template.tags
    ]


@router.get("", response_model=list[DeviceInstanceOut])
def list_instances(session: Session = Depends(get_session)):
    return session.query(DeviceInstance).all()


@router.post("", response_model=DeviceInstanceOut)
def create_instance(payload: DeviceInstanceIn, session: Session = Depends(get_session)):
    """Onboard a single device: from a template (tags inherited) or fully
    custom (tags supplied inline via tag_overrides)."""
    instance = DeviceInstance(
        org_id=payload.org_id, site_id=payload.site_id, gateway_id=payload.gateway_id,
        template_id=payload.template_id, name=payload.name, protocol=payload.protocol,
        connection_config=payload.connection_config, poll_interval_seconds=payload.poll_interval_seconds,
        status="active",
    )
    tags = _tags_from_template(session, payload.template_id)
    tags += [DeviceInstanceTag(**t.model_dump()) for t in payload.tag_overrides]
    instance.tags = tags
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return instance


@router.get("/{device_id}", response_model=DeviceInstanceDetailOut)
def get_instance(device_id: str, session: Session = Depends(get_session)):
    instance = session.get(DeviceInstance, device_id)
    if not instance:
        raise HTTPException(404, "Device not found")
    return instance


@router.post("/bulk-csv")
async def bulk_create_from_csv(
    template_id: str,
    org_id: str,
    site_id: str,
    gateway_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Onboard n devices of the same type at once. CSV columns:
    device_name, host_or_endpoint, port, unit_id_or_node_prefix
    """
    template = session.get(DeviceTemplate, template_id)
    if not template:
        raise HTTPException(400, "Unknown template_id")

    raw = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    created, errors = [], []

    for row_num, row in enumerate(reader, start=2):  # header is row 1
        try:
            if template.protocol == "modbus":
                connection_config = {
                    "host": row["host_or_endpoint"],
                    "port": int(row.get("port") or 502),
                    "unit_id": int(row.get("unit_id_or_node_prefix") or 1),
                }
            else:
                connection_config = {
                    "endpoint": row["host_or_endpoint"],
                    "browse_name": row.get("unit_id_or_node_prefix") or template.name,
                }
            instance = DeviceInstance(
                org_id=org_id, site_id=site_id, gateway_id=gateway_id, template_id=template_id,
                name=row["device_name"], protocol=template.protocol,
                connection_config=connection_config, status="active",
            )
            instance.tags = _tags_from_template(session, template_id)
            session.add(instance)
            session.flush()
            created.append(instance.id)
        except Exception as exc:
            errors.append({"row": row_num, "error": str(exc)})

    session.commit()
    return {"created": created, "errors": errors}


@router.post("/test-connection")
async def test_connection(payload: TestConnectionRequest):
    """Ask the target gateway to attempt one live read before saving the
    device, so a bad IP/register/browse-path is caught during onboarding."""
    return await request_test_connection(
        payload.gateway_id, payload.protocol, payload.connection_config,
        [t.model_dump() for t in payload.tags],
    )
