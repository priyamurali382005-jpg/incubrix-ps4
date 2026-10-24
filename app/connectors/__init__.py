from app import config
from app.connectors.assisted import AssistedConnector
from app.connectors.devto import DevtoConnector
from app.connectors.discourse import DiscourseConnector
from app.connectors.webhook import WebhookConnector
from app.errors import make_error


REGISTRY = {
    connector.key: connector
    for connector in (
        DiscourseConnector,
        DevtoConnector,
        WebhookConnector,
        AssistedConnector,
    )
}


def get_connector(key, client=None):
    if key not in REGISTRY:
        raise make_error("CONNECTOR_NOT_FOUND", f"No connector '{key}'.")

    if key in config.DISABLED_CONNECTORS:
        raise make_error("CONNECTOR_DISABLED", f"Connector '{key}' is switched off.")

    return REGISTRY[key](client=client)
