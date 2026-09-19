"""Seeds one demo org/site/gateway plus a template + onboarded instance for
each of the two simulators, so `docker compose up` shows live data with no
manual setup. Also doubles as the reference example for how onboarding via
the API is meant to work (see README.md).
"""
from sqlalchemy.orm import Session

from .models import (
    DeviceInstance,
    DeviceInstanceTag,
    DeviceTemplate,
    Gateway,
    Organization,
    Site,
    TemplateTag,
)

ORG_ID = "org-demo"
SITE_ID = "site-demo"
GATEWAY_ID = "edge-gateway-1"
MODBUS_TEMPLATE_ID = "tmpl-modbus-pump"
OPCUA_TEMPLATE_ID = "tmpl-opcua-pumpstation"


def seed_if_empty(session: Session):
    if session.get(Organization, ORG_ID):
        return

    # No relationship() is declared between Organization/Site/Gateway, so the
    # unit-of-work flush order isn't inferred from their FKs automatically -
    # flush each parent before adding its child to avoid inserting out of order.
    session.add(Organization(id=ORG_ID, name="Demo Org"))
    session.flush()
    session.add(Site(id=SITE_ID, org_id=ORG_ID, name="Demo Site"))
    session.flush()
    session.add(Gateway(id=GATEWAY_ID, site_id=SITE_ID, name="edge-gateway-1"))
    session.flush()

    modbus_template = DeviceTemplate(
        id=MODBUS_TEMPLATE_ID,
        name="Generic Modbus Pump Transmitter",
        manufacturer="Generic",
        model="MB-100",
        category="pump",
        protocol="modbus",
        description="Temperature/pressure/run-hours over Modbus TCP holding registers.",
    )
    session.add(modbus_template)
    session.flush()
    modbus_tags = [
        TemplateTag(
            template_id=modbus_template.id, tag_key="temperature_c", display_name="Temperature",
            data_type="float", unit="C", scale=0.1,
            protocol_config={"register_type": "holding", "address": 0, "count": 1},
        ),
        TemplateTag(
            template_id=modbus_template.id, tag_key="pressure_kpa", display_name="Pressure",
            data_type="float", unit="kPa", scale=0.1,
            protocol_config={"register_type": "holding", "address": 1, "count": 1},
        ),
        TemplateTag(
            template_id=modbus_template.id, tag_key="run_hours", display_name="Run Hours",
            data_type="int", unit="h", scale=1.0,
            protocol_config={"register_type": "holding", "address": 2, "count": 1},
        ),
    ]
    session.add_all(modbus_tags)

    opcua_template = DeviceTemplate(
        id=OPCUA_TEMPLATE_ID,
        name="Generic OPC-UA Pump Station",
        manufacturer="Generic",
        model="OPCUA-PS1",
        category="pump",
        protocol="opcua",
        description="Temperature/vibration/running-status over OPC-UA.",
    )
    session.add(opcua_template)
    session.flush()
    opcua_tags = [
        TemplateTag(
            template_id=opcua_template.id, tag_key="temperature_c", display_name="Temperature",
            data_type="float", unit="C", scale=1.0, protocol_config={"browse_path": ["Temperature"]},
        ),
        TemplateTag(
            template_id=opcua_template.id, tag_key="vibration_mm_s", display_name="Vibration",
            data_type="float", unit="mm/s", scale=1.0, protocol_config={"browse_path": ["Vibration"]},
        ),
        TemplateTag(
            template_id=opcua_template.id, tag_key="running_status", display_name="Running",
            data_type="bool", unit=None, scale=1.0, protocol_config={"browse_path": ["RunningStatus"]},
        ),
    ]
    session.add_all(opcua_tags)
    session.flush()

    modbus_instance = DeviceInstance(
        id="device-modbus-pump-1",
        org_id=ORG_ID, site_id=SITE_ID, gateway_id=GATEWAY_ID, template_id=modbus_template.id,
        name="Pump 1 (Modbus)", protocol="modbus",
        connection_config={"host": "modbus-sim", "port": 502, "unit_id": 1},
        poll_interval_seconds=1.0, status="active",
    )
    session.add(modbus_instance)
    session.flush()
    session.add_all([
        DeviceInstanceTag(
            device_instance_id=modbus_instance.id, tag_key=t.tag_key, display_name=t.display_name,
            data_type=t.data_type, unit=t.unit, scale=t.scale, protocol_config=t.protocol_config,
        )
        for t in modbus_tags
    ])

    opcua_instance = DeviceInstance(
        id="device-opcua-pumpstation-1",
        org_id=ORG_ID, site_id=SITE_ID, gateway_id=GATEWAY_ID, template_id=opcua_template.id,
        name="Pump Station 1 (OPC-UA)", protocol="opcua",
        connection_config={
            "endpoint": "opc.tcp://opcua-sim:4840/freeopcua/server/",
            "browse_name": "PumpStation1",
        },
        poll_interval_seconds=1.0, status="active",
    )
    session.add(opcua_instance)
    session.flush()
    session.add_all([
        DeviceInstanceTag(
            device_instance_id=opcua_instance.id, tag_key=t.tag_key, display_name=t.display_name,
            data_type=t.data_type, unit=t.unit, scale=t.scale, protocol_config=t.protocol_config,
        )
        for t in opcua_tags
    ])

    session.commit()
