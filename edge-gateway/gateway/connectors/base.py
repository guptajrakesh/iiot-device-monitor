from abc import ABC, abstractmethod


class Connector(ABC):
    """Common interface every protocol adapter implements.

    device_config shape (as returned by GET /api/gateways/{id}/config):
      {
        "device_id": str,
        "connection_config": dict,   # protocol-specific
        "tags": [{"tag_key": str, "protocol_config": dict, "scale": float}],
      }
    """

    def __init__(self, device_config: dict):
        self.device_config = device_config
        self.device_id = device_config["device_id"]

    @abstractmethod
    async def connect(self):
        ...

    @abstractmethod
    async def read_tags(self) -> list[dict]:
        """Return [{tag_id, value, quality, timestamp}, ...] for every configured tag."""
        ...

    @abstractmethod
    async def close(self):
        ...
