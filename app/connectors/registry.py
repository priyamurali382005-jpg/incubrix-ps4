from app.connectors.base import Connector


class ConnectorRegistry:
    def __init__(self):
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        self._connectors[connector.name] = connector

    def get(self, name: str) -> Connector:
        if name not in self._connectors:
            raise KeyError(f"Connector not registered: {name}")
        return self._connectors[name]

    def list_connectors(self) -> list[str]:
        return sorted(self._connectors.keys())
