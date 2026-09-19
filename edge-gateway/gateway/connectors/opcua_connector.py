import time

from asyncua import Client

from .base import Connector


class OpcUaConnector(Connector):
    """OPC-UA push (subscriptions) would be lower-latency, but Phase 1 keeps
    a uniform poll loop across protocols for simplicity; swapping this to a
    MonitoredItem subscription later doesn't change the Connector interface.

    Tags are resolved by walking browse names from the device's root object
    (connection_config["browse_name"]) rather than hardcoding NodeIds, so the
    gateway doesn't need to know the server's namespace index in advance.
    """

    def __init__(self, device_config: dict):
        super().__init__(device_config)
        self.client: Client | None = None
        self._resolved: dict[str, object] = {}

    async def connect(self):
        cc = self.device_config["connection_config"]
        self.client = Client(url=cc["endpoint"])
        await self.client.connect()
        device_node = await self._find_child(self.client.nodes.objects, cc["browse_name"])
        for tag in self.device_config["tags"]:
            node = device_node
            for name in tag["protocol_config"]["browse_path"]:
                node = await self._find_child(node, name)
            self._resolved[tag["tag_key"]] = node

    @staticmethod
    async def _find_child(parent_node, name: str):
        for child in await parent_node.get_children():
            browse_name = await child.read_browse_name()
            if browse_name.Name == name:
                return child
        raise RuntimeError(f"OPC-UA node '{name}' not found under {parent_node}")

    async def read_tags(self) -> list[dict]:
        readings = []
        ts = time.time()
        for tag_id, node in self._resolved.items():
            try:
                value = await node.read_value()
                if isinstance(value, bool):
                    value = float(value)  # readings.value is numeric; store digital tags as 0.0/1.0
                readings.append({"tag_id": tag_id, "value": value, "quality": "good", "timestamp": ts})
            except Exception:
                readings.append({"tag_id": tag_id, "value": None, "quality": "bad", "timestamp": ts})
        return readings

    async def close(self):
        if self.client:
            await self.client.disconnect()
