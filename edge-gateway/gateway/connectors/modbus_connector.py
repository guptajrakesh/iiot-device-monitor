import time

from pymodbus.client import AsyncModbusTcpClient

from .base import Connector


class ModbusConnector(Connector):
    """Modbus has no push/subscribe model, so we poll registers every cycle.

    Phase 1 supports holding registers only (function code 3) - the common
    case for transmitters/PLCs; input/coil/discrete registers are a
    straightforward follow-up using the same read-loop shape.
    """

    def __init__(self, device_config: dict):
        super().__init__(device_config)
        self.client: AsyncModbusTcpClient | None = None

    async def connect(self):
        cc = self.device_config["connection_config"]
        self.client = AsyncModbusTcpClient(cc["host"], port=cc.get("port", 502))
        connected = await self.client.connect()
        if not connected:
            raise ConnectionError(f"Could not reach Modbus device at {cc['host']}:{cc.get('port', 502)}")

    async def read_tags(self) -> list[dict]:
        readings = []
        ts = time.time()
        unit = self.device_config["connection_config"].get("unit_id", 1)
        for tag in self.device_config["tags"]:
            pc = tag["protocol_config"]
            tag_id = tag["tag_key"]
            try:
                result = await self.client.read_holding_registers(
                    pc["address"], count=pc.get("count", 1), slave=unit
                )
                if result.isError():
                    readings.append({"tag_id": tag_id, "value": None, "quality": "bad", "timestamp": ts})
                    continue
                raw = result.registers[0]
                value = raw * tag.get("scale", 1)
                readings.append({"tag_id": tag_id, "value": value, "quality": "good", "timestamp": ts})
            except Exception:
                readings.append({"tag_id": tag_id, "value": None, "quality": "bad", "timestamp": ts})
        return readings

    async def close(self):
        if self.client:
            self.client.close()
