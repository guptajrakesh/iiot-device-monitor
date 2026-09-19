# IIoT Device Monitor

Real-time device status app for OPC-UA and Modbus devices. See
`C:\Users\admin\.claude\plans\iiot-device-monitoring-app.md` for the base
architecture and `can-i-sell-this-virtual-emerson.md` for the device
template/instance onboarding design this implements.

## Run it

```bash
docker compose up --build
```

Then open http://localhost:8000 - it seeds a demo org/site/gateway plus one
Modbus and one OPC-UA device (matching the two simulator containers) and
shows their live values updating over a WebSocket.

No real PLC or OPC-UA server is needed: `modbus-sim` and `opcua-sim` are
fake devices with drifting values, standing in for real hardware during
development (see `simulators/`).

## Architecture

```
[modbus-sim / opcua-sim] --OPC-UA/Modbus--> [edge-gateway]
                                                  |  normalizes, buffers locally on outage
                                                  v
                                          MQTT (mosquitto)
                                                  |
                                                  v
                                    [backend: ingest -> TimescaleDB]
                                                  |
                                                  v
                                    WebSocket -> dashboard (backend/app/static)
```

The edge gateway never receives inbound connections - it polls
`GET /api/gateways/{gateway_id}/config` for its device/tag assignment and
publishes outbound to MQTT, matching how a real deployment would reach
devices sitting on an isolated OT network from a cloud backend.

## Onboarding devices (Device Template + Device Instance)

Rather than hand-writing config per device, you define a **template** once
per device *type* (protocol + full tag/register map), then create cheap
**instances** from it that only supply connection details.

**1. Create a template** (already done for you by the seed data - this is
what it looks like):

```bash
curl -X POST http://localhost:8000/api/templates -H "Content-Type: application/json" -d '{
  "name": "Generic Modbus Pump Transmitter",
  "protocol": "modbus",
  "tags": [
    {"tag_key": "temperature_c", "display_name": "Temperature", "scale": 0.1,
     "protocol_config": {"register_type": "holding", "address": 0, "count": 1}}
  ]
}'
```

**2. Onboard one device from a template:**

```bash
curl -X POST http://localhost:8000/api/devices -H "Content-Type: application/json" -d '{
  "org_id": "org-demo", "site_id": "site-demo", "gateway_id": "edge-gateway-1",
  "template_id": "tmpl-modbus-pump",
  "name": "Pump 4 (Modbus)", "protocol": "modbus",
  "connection_config": {"host": "modbus-sim", "port": 502, "unit_id": 4}
}'
```

The gateway picks this up on its next config poll (every 15s) - no restart
needed - and the new device appears on the dashboard.

**3. Onboard n devices at once (bulk CSV)** - see `sample_bulk_onboard.csv`:

```bash
curl -X POST "http://localhost:8000/api/devices/bulk-csv?template_id=tmpl-modbus-pump&org_id=org-demo&site_id=site-demo&gateway_id=edge-gateway-1" \
  -F "file=@sample_bulk_onboard.csv"
```

Note: the sample CSV points extra "devices" at the same `modbus-sim`
container with different unit IDs, purely to demonstrate the bulk path
against the one simulator available in dev - the simulator only actually
serves unit ID 1, so those extra rows will show `quality: bad` on the
dashboard rather than real data. Against real hardware, each row would be a
different physical device's real IP/unit ID.

**4. Test a connection before saving** (what an onboarding UI would call
before letting you hit save):

```bash
curl -X POST http://localhost:8000/api/devices/test-connection -H "Content-Type: application/json" -d '{
  "gateway_id": "edge-gateway-1", "protocol": "modbus",
  "connection_config": {"host": "modbus-sim", "port": 502, "unit_id": 1},
  "tags": [{"tag_key": "temperature_c", "display_name": "Temperature", "scale": 0.1,
            "protocol_config": {"register_type": "holding", "address": 0, "count": 1}}]
}'
```

## What's built vs. what's next

Built: template/instance data model, single + bulk onboarding, gateway
hot-reload via config polling, test-connection round trip, MQTT ingest into
TimescaleDB, live WebSocket dashboard, local buffering on the gateway if the
broker connection drops.

Not yet built (next phase): an actual onboarding UI (template library +
device wizard screens - the API above is what it would call), Modbus RTU/
serial support, alarm thresholds, multi-tenant auth, and OPC-UA
subscriptions (Phase 1 polls OPC-UA on the same interval as Modbus rather
than using native push, to keep the gateway's poll loop uniform across
protocols).
