"""Fake OPC-UA device: a 'pump station' object exposing Temperature, Vibration
and RunningStatus variables (matches the "Generic OPC-UA Pump Station" template).

Tags are resolved by the gateway/backend via browse *name*, not NodeId, so the
exact namespace index assigned below does not need to be hardcoded anywhere else.
"""
import asyncio
import logging
import os
import random

from asyncua import Server

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("opcua-sim")


async def _handle_health_check(reader, writer):
    try:
        await reader.read(1024)
        body = b"OK"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
            + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
        )
        await writer.drain()
    except Exception:
        pass
    writer.close()


async def _run_health_server():
    # Some PaaS free tiers (e.g. Render) only offer the "Web Service" type,
    # which requires an HTTP port to consider the service "live" - raw
    # OPC-UA TCP on :4840 doesn't satisfy that check on its own. Harmless
    # locally: nothing publishes or depends on this port there.
    port = int(os.environ.get("PORT", "8080"))
    server = await asyncio.start_server(_handle_health_check, "0.0.0.0", port)
    log.info("Health-check listener on :%d (for PaaS deployments only)", port)
    async with server:
        await server.serve_forever()


async def main():
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
    idx = await server.register_namespace("http://iiot-demo.local")

    objects = server.nodes.objects
    device = await objects.add_object(idx, "PumpStation1")
    temperature = await device.add_variable(idx, "Temperature", 25.0)
    vibration = await device.add_variable(idx, "Vibration", 0.02)
    status = await device.add_variable(idx, "RunningStatus", True)
    for var in (temperature, vibration, status):
        await var.set_writable()

    asyncio.create_task(_run_health_server())
    log.info("OPC-UA simulator listening on 0.0.0.0:4840")
    async with server:
        while True:
            await asyncio.sleep(1)
            await temperature.write_value(25.0 + random.uniform(-1, 1))
            await vibration.write_value(round(random.uniform(0.01, 0.05), 3))
            await status.write_value(True)


if __name__ == "__main__":
    asyncio.run(main())
