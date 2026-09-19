import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import aiomqtt
from sqlalchemy import insert

from .db import SessionLocal
from .models import AlertEvent, AlertRule, Reading
from .notifier import notify
from .ws_manager import WSManager

log = logging.getLogger("mqtt-ingest")

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "8883"))
MQTT_CA_CERT = os.environ.get("MQTT_CA_CERT", "/certs/ca.crt")


def _mqtt_tls_params():
    if os.path.exists(MQTT_CA_CERT):
        return aiomqtt.TLSParameters(ca_certs=MQTT_CA_CERT)
    log.warning("MQTT CA cert not found at %s; connecting without TLS", MQTT_CA_CERT)
    return None

CONDITION_FUNCS = {
    "gt": lambda value, threshold: value > threshold,
    "gte": lambda value, threshold: value >= threshold,
    "lt": lambda value, threshold: value < threshold,
    "lte": lambda value, threshold: value <= threshold,
}


async def ingest_loop(ws_manager: WSManager, mqtt_host: str = MQTT_HOST, mqtt_port: int = MQTT_PORT):
    while True:
        try:
            async with aiomqtt.Client(mqtt_host, port=mqtt_port, tls_params=_mqtt_tls_params()) as client:
                await client.subscribe("iiot/+/readings")
                await client.subscribe("iiot/+/test-response/+")
                log.info("MQTT ingest connected, subscribed to readings and test-response topics")
                async for message in client.messages:
                    topic = str(message.topic)
                    if "/test-response/" in topic:
                        await _handle_test_response(message)
                    elif topic.endswith("/readings"):
                        await _handle_reading(message, ws_manager)
        except Exception as exc:
            log.warning("MQTT ingest connection lost (%s); retrying in 3s", exc)
            await asyncio.sleep(3)


async def _handle_reading(message, ws_manager: WSManager):
    try:
        payload = json.loads(message.payload)
    except Exception:
        log.exception("Failed to parse readings payload")
        return

    device_id = payload["device_id"]
    ts = datetime.fromtimestamp(payload["timestamp"], tz=timezone.utc)
    session = SessionLocal()
    try:
        for reading in payload["readings"]:
            session.execute(
                insert(Reading).values(
                    time=ts,
                    device_instance_id=device_id,
                    tag_key=reading["tag_id"],
                    value=reading["value"],
                    quality=reading["quality"],
                )
            )
        session.commit()
    except Exception:
        # A single bad reading (wrong type, out-of-range value, etc.) must not
        # take down the whole MQTT ingest connection for every other device.
        session.rollback()
        log.exception("Failed to store readings for device %s; dropping this batch", device_id)
        return
    finally:
        session.close()

    await ws_manager.broadcast(
        {"type": "reading", "device_id": device_id, "timestamp": payload["timestamp"], "readings": payload["readings"]}
    )

    for reading in payload["readings"]:
        await _evaluate_alerts(device_id, reading, ts, ws_manager)


def _event_to_dict(event: AlertEvent) -> dict:
    return {
        "id": event.id, "rule_id": event.rule_id, "device_instance_id": event.device_instance_id,
        "tag_key": event.tag_key, "condition": event.condition, "threshold": event.threshold,
        "value": event.value, "severity": event.severity, "status": event.status,
        "acknowledged": event.acknowledged,
        "triggered_at": event.triggered_at.isoformat() if event.triggered_at else None,
        "resolved_at": event.resolved_at.isoformat() if event.resolved_at else None,
    }


async def _evaluate_alerts(device_id: str, reading: dict, ts: datetime, ws_manager: WSManager):
    """Edge-triggered: creates an AlertEvent only on the transition into
    breach, and resolves it only on the transition back out - not once per
    reading while a threshold stays crossed."""
    value = reading["value"]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return

    session = SessionLocal()
    try:
        rules = session.query(AlertRule).filter_by(
            device_instance_id=device_id, tag_key=reading["tag_id"], enabled=True,
        ).all()
        for rule in rules:
            breached = CONDITION_FUNCS[rule.condition](value, rule.threshold)
            active_event = session.query(AlertEvent).filter_by(rule_id=rule.id, status="active").first()

            if breached and not active_event:
                event = AlertEvent(
                    rule_id=rule.id, device_instance_id=device_id, tag_key=rule.tag_key,
                    condition=rule.condition, threshold=rule.threshold, value=value,
                    severity=rule.severity, status="active", triggered_at=ts,
                )
                session.add(event)
                session.commit()
                session.refresh(event)
                notify(event)
                await ws_manager.broadcast({"type": "alert", "event": _event_to_dict(event)})
            elif not breached and active_event:
                active_event.status = "resolved"
                active_event.resolved_at = ts
                session.commit()
                await ws_manager.broadcast({"type": "alert", "event": _event_to_dict(active_event)})
    except Exception:
        session.rollback()
        log.exception("Alert evaluation failed for device %s tag %s", device_id, reading.get("tag_id"))
    finally:
        session.close()


async def _handle_test_response(message):
    from .mqtt_test import resolve_test_response

    try:
        payload = json.loads(message.payload)
        resolve_test_response(payload["request_id"], payload)
    except Exception:
        log.exception("Failed to handle test-response message")
