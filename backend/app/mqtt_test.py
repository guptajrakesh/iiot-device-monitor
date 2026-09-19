"""Backend side of the onboarding 'Test Connection' round trip.

The backend never reaches the gateway directly (gateways are outbound-only,
per the OT security posture in the design doc). Instead it publishes a
test-request and waits for the matching test-response, correlated by a
request_id, coming back through the persistent MQTT ingest subscription.
"""
import asyncio
import json
import os
import uuid

import aiomqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "8883"))
MQTT_CA_CERT = os.environ.get("MQTT_CA_CERT", "/certs/ca.crt")

_pending: dict[str, "asyncio.Future"] = {}


def _mqtt_tls_params():
    if os.path.exists(MQTT_CA_CERT):
        return aiomqtt.TLSParameters(ca_certs=MQTT_CA_CERT)
    return None


async def request_test_connection(
    gateway_id: str, protocol: str, connection_config: dict, tags: list[dict], timeout: float = 10
) -> dict:
    request_id = str(uuid.uuid4())
    future = asyncio.get_event_loop().create_future()
    _pending[request_id] = future
    payload = {
        "request_id": request_id,
        "protocol": protocol,
        "connection_config": connection_config,
        "tags": tags,
    }
    try:
        async with aiomqtt.Client(MQTT_HOST, port=MQTT_PORT, tls_params=_mqtt_tls_params()) as client:
            await client.publish(f"iiot/{gateway_id}/test-request", json.dumps(payload), qos=1)
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        return {"success": False, "error": "Gateway did not respond in time (is it online?)"}
    finally:
        _pending.pop(request_id, None)


def resolve_test_response(request_id: str, result: dict):
    future = _pending.get(request_id)
    if future and not future.done():
        future.set_result(result)
