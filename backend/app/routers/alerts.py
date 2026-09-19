from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import AlertEvent, AlertRule, DeviceInstance
from ..schemas import AlertEventOut, AlertRuleIn, AlertRuleOut

router = APIRouter(prefix="/api/alert-rules", tags=["alerts"])
events_router = APIRouter(prefix="/api/alert-events", tags=["alerts"])


@router.get("", response_model=list[AlertRuleOut])
def list_rules(device_instance_id: str | None = None, session: Session = Depends(get_session)):
    q = session.query(AlertRule)
    if device_instance_id:
        q = q.filter_by(device_instance_id=device_instance_id)
    return q.all()


@router.post("", response_model=AlertRuleOut)
def create_rule(payload: AlertRuleIn, session: Session = Depends(get_session)):
    if not session.get(DeviceInstance, payload.device_instance_id):
        raise HTTPException(400, "Unknown device_instance_id")
    rule = AlertRule(**payload.model_dump())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=AlertRuleOut)
def update_rule(rule_id: str, payload: AlertRuleIn, session: Session = Depends(get_session)):
    rule = session.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    session.commit()
    session.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, session: Session = Depends(get_session)):
    rule = session.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    session.delete(rule)
    session.commit()
    return {"deleted": rule_id}


@events_router.get("", response_model=list[AlertEventOut])
def list_events(status: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    q = session.query(AlertEvent).order_by(AlertEvent.triggered_at.desc())
    if status:
        q = q.filter_by(status=status)
    return q.limit(limit).all()


@events_router.post("/{event_id}/acknowledge", response_model=AlertEventOut)
def acknowledge_event(event_id: str, session: Session = Depends(get_session)):
    event = session.get(AlertEvent, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    event.acknowledged = True
    session.commit()
    session.refresh(event)
    return event
