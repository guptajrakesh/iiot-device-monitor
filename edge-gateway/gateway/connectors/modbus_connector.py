import time

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

from .base import Connector

_REGISTER_READ_METHODS = {"holding": "read_holding_registers", "input": "read_input_registers"}
_BIT_READ_METHODS = {"coil": "read_coils", "discrete": "read_discrete_inputs"}
_VALUE_TYPE_REGISTER_COUNT = {"uint16": 1, "int16": 1, "uint32": 2, "int32": 2, "float32": 2}
_ENDIAN = {"big": Endian.BIG, "little": Endian.LITTLE}


def _decode_registers(registers: list[int], value_type: str, byte_order: str, word_order: str):
    decoder = BinaryPayloadDecoder.fromRegisters(
        registers, byteorder=_ENDIAN[byte_order], wordorder=_ENDIAN[word_order]
    )
    return {
        "uint16": decoder.decode_16bit_uint,
        "int16": decoder.decode_16bit_int,
        "uint32": decoder.decode_32bit_uint,
        "int32": decoder.decode_32bit_int,
        "float32": decoder.decode_32bit_float,
    }[value_type]()


class ModbusConnector(Connector):
    """Modbus has no push/subscribe model, so we poll registers every cycle.

    protocol_config per tag:
      register_type: "holding" | "input" | "coil" | "discrete" (default "holding")
      address: int
      value_type: "uint16" | "int16" | "uint32" | "int32" | "float32" (default "uint16")
                  - only meaningful for holding/input; uint32/int32/float32 read
                    two consecutive registers and decode them as one value, the
                    common case for an analog transmitter reporting a 32-bit float.
      byte_order / word_order: "big" | "little" (default "big" for both) - the
                  16-bit-word and within-word byte ordering used for multi-register
                  values. Genuinely varies by device vendor; "big"/"big" (the
                  conventional ABCD layout) is the default, override per-tag for
                  devices that use a different convention.
    coil/discrete tags always read a single bit at `address`.
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
            register_type = pc.get("register_type", "holding")
            try:
                if register_type in _BIT_READ_METHODS:
                    method = getattr(self.client, _BIT_READ_METHODS[register_type])
                    result = await method(pc["address"], count=1, slave=unit)
                    if result.isError():
                        readings.append({"tag_id": tag_id, "value": None, "quality": "bad", "timestamp": ts})
                        continue
                    raw = float(result.bits[0])
                else:
                    value_type = pc.get("value_type", "uint16")
                    count = _VALUE_TYPE_REGISTER_COUNT.get(value_type, 1)
                    method_name = _REGISTER_READ_METHODS.get(register_type, "read_holding_registers")
                    result = await getattr(self.client, method_name)(pc["address"], count=count, slave=unit)
                    if result.isError():
                        readings.append({"tag_id": tag_id, "value": None, "quality": "bad", "timestamp": ts})
                        continue
                    raw = _decode_registers(
                        result.registers, value_type, pc.get("byte_order", "big"), pc.get("word_order", "big")
                    )
                value = raw * tag.get("scale", 1)
                readings.append({"tag_id": tag_id, "value": value, "quality": "good", "timestamp": ts})
            except Exception:
                readings.append({"tag_id": tag_id, "value": None, "quality": "bad", "timestamp": ts})
        return readings

    async def close(self):
        if self.client:
            self.client.close()
