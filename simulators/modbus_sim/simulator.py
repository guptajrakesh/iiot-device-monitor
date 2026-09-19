"""Fake Modbus TCP device: a 'pump transmitter' exercising every register
type and value width the edge gateway's ModbusConnector supports, so those
code paths can be verified against a real Modbus TCP round trip rather than
only unit-tested in isolation.

Holding registers (function code 3):
  0: temperature_c * 10           (uint16)
  1: pressure_kpa * 10            (uint16)
  2: run_hours                    (uint16)
  10-11: flow_rate_lpm            (float32, big-endian word/byte order)
Input registers (function code 4):
  0: raw_sensor_input             (uint16) - read-only process value
Coils (function code 1):
  0: running_status               (bit) - flips a few times a minute
"""
import asyncio
import logging
import os
import random

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.constants import Endian

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("modbus-sim")


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
    # Modbus TCP on :502 doesn't satisfy that check on its own. Harmless
    # locally: nothing publishes or depends on this port there.
    port = int(os.environ.get("PORT", "8080"))
    server = await asyncio.start_server(_handle_health_check, "0.0.0.0", port)
    log.info("Health-check listener on :%d (for PaaS deployments only)", port)
    async with server:
        await server.serve_forever()


async def simulate_values(context: ModbusServerContext):
    slave_ctx: ModbusSlaveContext = context[0]
    run_hours = 0
    tick = 0
    while True:
        temperature = int((22 + random.uniform(-2, 2)) * 10)
        pressure = int((1000 + random.uniform(-30, 30)) * 10)
        run_hours += 1
        slave_ctx.setValues(3, 0, [temperature, pressure, run_hours])

        flow_rate = 45.0 + random.uniform(-3, 3)
        builder = BinaryPayloadBuilder(byteorder=Endian.BIG, wordorder=Endian.BIG)
        builder.add_32bit_float(flow_rate)
        slave_ctx.setValues(3, 10, builder.to_registers())

        raw_input = int((500 + random.uniform(-20, 20)))
        slave_ctx.setValues(4, 0, [raw_input])

        tick += 1
        slave_ctx.setValues(1, 0, [1 if (tick // 5) % 2 == 0 else 0])

        await asyncio.sleep(1)


async def main():
    store = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [0] * 20),
        ir=ModbusSequentialDataBlock(0, [0] * 5),
        co=ModbusSequentialDataBlock(0, [0] * 5),
    )
    context = ModbusServerContext(slaves=store, single=True)
    asyncio.create_task(simulate_values(context))
    asyncio.create_task(_run_health_server())
    log.info("Modbus TCP simulator listening on 0.0.0.0:502")
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", 502))


if __name__ == "__main__":
    asyncio.run(main())
