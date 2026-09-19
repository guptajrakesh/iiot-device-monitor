import asyncio
import json
import logging
import os
import time

import aiomqtt
import httpx

from .buffer import LocalBuffer
from .connectors.modbus_connector import ModbusConnector
from .connectors.opcua_connector import OpcUaConnector

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("edge-gateway")

CONNECTOR_TYPES = {"modbus": ModbusConnector, "opcua": OpcUaConnector}

GATEWAY_ID = os.environ.get("GATEWAY_ID", "edge-gateway-1")
# BACKEND_HOST/PORT (split) take priority over BACKEND_URL when set - some hosting
# platforms (e.g. Render's Blueprint env-var linking) can only inject one property
# (host or port) per variable, not a pre-assembled URL.
_BACKEND_HOST = os.environ.get("BACKEND_HOST")
if _BACKEND_HOST:
    BACKEND_URL = f"http://{_BACKEND_HOST}:{os.environ.get('BACKEND_PORT', '8000')}"
else:
    BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "8883"))
MQTT_CA_CERT = os.environ.get("MQTT_CA_CERT", "/certs/ca.crt")
CONFIG_POLL_SECONDS = int(os.environ.get("CONFIG_POLL_SECONDS", "15"))


def _mqtt_tls_params():
    # The broker uses a locally-generated self-signed CA (see mosquitto/gen-certs.sh);
    # trusting that CA file is what lets the client verify the broker's certificate.
    if os.path.exists(MQTT_CA_CERT):
        return aiomqtt.TLSParameters(ca_certs=MQTT_CA_CERT)
    log.warning("MQTT CA cert not found at %s; connecting without TLS", MQTT_CA_CERT)
    return None


class Gateway:
    """Pulls its device/tag assignment from the backend instead of a static
    file, so onboarding a device through the API/UI takes effect here within
    one poll cycle - no gateway redeploy needed.
    """

    def __init__(self):
        self.buffer = LocalBuffer()
        self.mqtt_client: aiomqtt.Client | None = None
        self.device_tasks: dict[str, asyncio.Task] = {}
        self.connectors: dict[str, object] = {}

    async def fetch_config(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BACKEND_URL}/api/gateways/{GATEWAY_ID}/config")
            resp.raise_for_status()
            return resp.json()["devices"]

    async def reconcile(self, devices: list[dict]):
        current_ids = set(self.device_tasks)
        new_ids = {d["device_id"] for d in devices}

        for device_id in current_ids - new_ids:
            self.device_tasks.pop(device_id).cancel()
            connector = self.connectors.pop(device_id, None)
            if connector:
                await connector.close()
            log.info("Device %s no longer assigned to this gateway - stopped polling", device_id)

        for device in devices:
            device_id = device["device_id"]
            if device_id in self.device_tasks:
                continue
            connector_cls = CONNECTOR_TYPES[device["protocol"]]
            connector = connector_cls(device)
            try:
                await connector.connect()
            except Exception as exc:
                log.error("Failed to connect to device %s (%s): %s", device_id, device["name"], exc)
                continue
            self.connectors[device_id] = connector
            self.device_tasks[device_id] = asyncio.create_task(
                self.poll_device(device_id, connector, device.get("poll_interval_seconds", 1))
            )
            log.info("Onboarded device %s (%s) via %s", device_id, device["name"], device["protocol"])

    async def config_poll_loop(self):
        while True:
            try:
                devices = await self.fetch_config()
                await self.reconcile(devices)
            except Exception as exc:
                log.warning("Config fetch from backend failed: %s", exc)
            await asyncio.sleep(CONFIG_POLL_SECONDS)

    async def publish(self, topic: str, payload: dict):
        message = json.dumps(payload)
        if self.mqtt_client is None:
            self.buffer.enqueue({"topic": topic, "payload": payload})
            return
        try:
            await self.mqtt_client.publish(topic, message, qos=1)
        except Exception as exc:
            log.warning("MQTT publish failed (%s); buffering locally", exc)
            self.buffer.enqueue({"topic": topic, "payload": payload})

    async def flush_buffer_loop(self):
        while True:
            await asyncio.sleep(5)
            if self.mqtt_client is None or self.buffer.count() == 0:
                continue
            rows = self.buffer.pending_batch(limit=50)
            sent_ids = []
            for row_id, payload_json in rows:
                item = json.loads(payload_json)
                try:
                    await self.mqtt_client.publish(item["topic"], json.dumps(item["payload"]), qos=1)
                    sent_ids.append(row_id)
                except Exception:
                    break
            if sent_ids:
                self.buffer.remove(sent_ids)
                log.info("Flushed %d buffered readings after reconnect", len(sent_ids))

    async def poll_device(self, device_id: str, connector, interval: float):
        while True:
            readings = await connector.read_tags()
            payload = {"device_id": device_id, "timestamp": time.time(), "readings": readings}
            await self.publish(f"iiot/{device_id}/readings", payload)
            await asyncio.sleep(interval)

    async def handle_test_request(self, message):
        payload = json.loads(message.payload)
        request_id = payload["request_id"]
        result = {"request_id": request_id, "success": False}
        connector = None
        try:
            connector_cls = CONNECTOR_TYPES[payload["protocol"]]
            connector = connector_cls({
                "device_id": f"test-{request_id}",
                "connection_config": payload["connection_config"],
                "tags": payload["tags"],
            })
            await connector.connect()
            result["readings"] = await connector.read_tags()
            result["success"] = True
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            if connector:
                try:
                    await connector.close()
                except Exception:
                    pass
        await self.publish(f"iiot/{GATEWAY_ID}/test-response/{request_id}", result)

    async def test_listener_loop(self, client: aiomqtt.Client):
        await client.subscribe(f"iiot/{GATEWAY_ID}/test-request")
        async for message in client.messages:
            asyncio.create_task(self.handle_test_request(message))

    async def run(self):
        async with aiomqtt.Client(MQTT_HOST, port=MQTT_PORT, tls_params=_mqtt_tls_params()) as client:
            self.mqtt_client = client
            await asyncio.gather(
                self.config_poll_loop(),
                self.flush_buffer_loop(),
                self.test_listener_loop(client),
            )


async def _handle_health_check(reader, writer):
    try:
        await reader.read(1024)
        body = b"OK"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
    except Exception:
        pass
    writer.close()


async def _run_health_server():
    # Some PaaS free tiers (e.g. Render) only offer the "Web Service" type on
    # their free plan, even for something like this gateway with nothing to
    # actually serve - this exists purely so such a platform has a port to
    # health-check. Harmless locally: nothing publishes or depends on this port.
    port = int(os.environ.get("PORT", "8080"))
    server = await asyncio.start_server(_handle_health_check, "0.0.0.0", port)
    log.info("Health-check listener on :%d (for PaaS deployments only)", port)
    async with server:
        await server.serve_forever()


async def main():
    asyncio.create_task(_run_health_server())
    gateway = Gateway()
    while True:
        try:
            await gateway.run()
        except Exception as exc:
            log.error("Gateway connection loop crashed: %s; retrying in 5s", exc)
            gateway.mqtt_client = None
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
