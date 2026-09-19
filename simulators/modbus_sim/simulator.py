"""Fake Modbus TCP device: a 'pump transmitter' exposing temperature, pressure
and a run-hours counter as holding registers, drifting like a real sensor would.

Register map (matches the "Generic Modbus Pump Transmitter" device template):
  0: temperature_c * 10
  1: pressure_kpa * 10
  2: run_hours (integer counter)
"""
import asyncio
import logging
import random

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("modbus-sim")


async def simulate_values(context: ModbusServerContext):
    slave_ctx: ModbusSlaveContext = context[0]
    run_hours = 0
    while True:
        temperature = int((22 + random.uniform(-2, 2)) * 10)
        pressure = int((1000 + random.uniform(-30, 30)) * 10)
        run_hours += 1
        slave_ctx.setValues(3, 0, [temperature, pressure, run_hours])
        await asyncio.sleep(1)


async def main():
    store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * 10))
    context = ModbusServerContext(slaves=store, single=True)
    asyncio.create_task(simulate_values(context))
    log.info("Modbus TCP simulator listening on 0.0.0.0:502")
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", 502))


if __name__ == "__main__":
    asyncio.run(main())
