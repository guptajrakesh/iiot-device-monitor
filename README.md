# IIoT Device Monitor

Real-time status, device onboarding, and threshold alerting for industrial devices connected over
**OPC-UA** or **Modbus TCP**. An edge gateway polls devices on-site and publishes over TLS-encrypted
MQTT to a backend that stores history in TimescaleDB, pushes live updates over WebSocket, and evaluates
alert rules.

No real hardware is required to run this — two simulators stand in for an OPC-UA and a Modbus device.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker Compose v2, included by default)
- Ports `8000`, `8883`, `5432`, `5020`, `4840` free on your host

## Quick start

```bash
git clone https://github.com/guptajrakesh/iiot-device-monitor.git
cd iiot-device-monitor
docker compose up --build
```

First run takes a few minutes (pulling base images, installing Python dependencies, generating a
local TLS certificate for MQTT). Once it settles:

- **Dashboard**: http://localhost:8000
- **Walkthrough / architecture doc**: http://localhost:8000/walkthrough.html (also linked from the
  dashboard's menu bar)

It comes up pre-seeded with a demo org/site/gateway and two devices already streaming live data —
one Modbus, one OPC-UA — so there's something to look at immediately, no setup needed.

To stop everything: `docker compose down` (add `-v` to also wipe the database and generated certs).

## What's running

| Service | Purpose | Host port |
|---|---|---|
| `backend` | FastAPI app: REST API, MQTT ingest, WebSocket, alert evaluation | `8000` |
| `edge-gateway` | Polls the simulated devices, publishes readings over MQTT | — |
| `mosquitto` | MQTT broker, TLS-only | `8883` |
| `timescaledb` | Postgres + TimescaleDB, stores every reading | `5432` |
| `modbus-sim` | Fake Modbus TCP device (drifting temperature/pressure/run-hours) | `5020` |
| `opcua-sim` | Fake OPC-UA device (drifting temperature/vibration/status) | `4840` |
| `cert-init` | One-shot: generates the local MQTT TLS certificate, then exits | — |

## Using the app

The dashboard has four tabs:

- **Live Dashboard** — KPI summary, one card per device, sparklines per tag. Click any tag row to open
  a historical trend chart (1h / 6h / 24h / 7d, backed by TimescaleDB's `time_bucket()`).
- **Device Templates** — define a device *type* once (protocol + full tag/register map), then reuse it.
- **Devices** — onboard a device from a template (with a live **Test Connection** check before saving),
  onboard many at once from a CSV (see `sample_bulk_onboard.csv`), or define a one-off custom device.
- **Alerts** — set a threshold on any device/tag (`>`, `>=`, `<`, `<=`), see the live event feed, and
  acknowledge active alerts. Notifications are logged to the backend console in the exact shape a real
  email/SMS would take (see `backend/app/notifier.py`) — wiring up a real provider later doesn't touch
  anything else in the pipeline.

New devices onboarded through the UI or API go live within one gateway poll cycle (~15s) — no restart.

## Inspecting the data directly

Connect any Postgres client (DBeaver, TablePlus, pgAdmin, `psql`) to:

| Field | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `iiot` |
| User / Password | `iiot` / `iiot` |

Or from the command line:

```bash
docker compose exec timescaledb psql -U iiot -d iiot -c \
  "SELECT device_instance_id, tag_key, value, time FROM readings ORDER BY time DESC LIMIT 10;"
```

## Architecture

```
[Device] --OPC-UA/Modbus--> [Edge Gateway] --MQTT over TLS--> [Mosquitto]
                                  |  buffers to disk on outage         |
                                  |  polls backend for its config      | subscribe
                                  v                                    v
                         [Backend API]                        [Ingest Service]
                                                                   |        |
                                                            insert |        | broadcast + evaluate
                                                                   v        v
                                                         [TimescaleDB]  [WebSocket] -> [Dashboard]
                                                                             |
                                                                     [Alert Rules] -> [Notifier]
```

The gateway only ever makes outbound connections (poll the backend, publish to MQTT) — nothing
downstream can reach back into the device network. See `http://localhost:8000/walkthrough.html` for
diagrams and a full walkthrough of both this data-flow and the device onboarding design.

## Security notes

- MQTT is TLS-encrypted against a self-signed CA generated automatically on first run
  (`mosquitto/gen-certs.sh`) — real, not aspirational.
- **There is no authentication anywhere in this app.** Every REST endpoint and the MQTT broker itself
  (`allow_anonymous true`) are open to anyone who can reach them. This is fine for local development;
  it is the single biggest gap before deploying this anywhere beyond your own machine.

## Known limitations

- Modbus RTU / serial devices aren't supported — TCP only.
- OPC-UA connects anonymously only — no username/password or certificate-based security.
- OPC-UA is polled on the same loop as Modbus rather than using native subscriptions.

Modbus itself now supports all four register types (holding/input/coil/discrete) and multi-register
values (uint32/int32/float32 spanning two registers, with configurable byte/word order) — see
`protocol_config` in `edge-gateway/gateway/connectors/modbus_connector.py`.

## Project layout

```
backend/           FastAPI app (REST API, MQTT ingest, alert engine, static dashboard)
edge-gateway/       Polls devices, publishes MQTT, buffers on outage
simulators/         Fake Modbus + OPC-UA devices for development
mosquitto/          Broker config + TLS cert generation script
docker-compose.yml  Wires all of the above together
```
