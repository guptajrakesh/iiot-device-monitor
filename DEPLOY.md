# Deploying to Render (free tier)

This deploys the whole stack — backend, MQTT broker, both simulators, and the edge gateway — as
separate free-tier services on [Render](https://render.com), backed by a free
[Timescale Cloud](https://console.cloud.timescale.com) database. Same pattern as this org's other
project (a single web service + an external managed Postgres), just split across more services since
this app has more moving parts.

**No credit card should be required for either signup**, based on current public info as of this
writing — Timescale Cloud's free trial/Beta plan explicitly doesn't ask for one, and Render's free
tier generally doesn't either. That said, **if either site asks you for card details at any point,
stop and don't enter them** — come back here and we'll figure out an alternative rather than proceed.

## What you'll end up with

| Render service | Type | What it is |
|---|---|---|
| `iiot-backend` | Web Service | The API + dashboard — this is the URL you'll actually visit |
| `iiot-mosquitto` | Private Service | MQTT broker (plaintext — see note below) |
| `iiot-modbus-sim` | Private Service | Fake Modbus device |
| `iiot-opcua-sim` | Private Service | Fake OPC-UA device |
| `iiot-edge-gateway` | Background Worker | Polls the simulators, publishes to MQTT |

The database lives outside Render entirely, on Timescale Cloud.

**Note on security**: the deployed MQTT broker runs without TLS (`mosquitto/Dockerfile.cloud`),
unlike local `docker compose up` which uses a real TLS-encrypted broker. Render's private services
aren't reachable from the public internet at all — only other services in the same Render account can
reach them — so this trades the local setup's defense-in-depth for simplicity, which is a reasonable
call for a demo deployment but worth knowing about. Separately, and more importantly: **this app has
no authentication anywhere**. The backend's URL, once deployed, is a normal public web address with
zero login — anyone who has the link can onboard/delete devices, read all data, and change alert
rules. Don't put anything sensitive behind it, and treat the link as effectively public.

## Steps

### 1. Create a free Timescale Cloud database

1. Go to [console.cloud.timescale.com](https://console.cloud.timescale.com) and sign up (email only).
2. Create a new service (the default Postgres + TimescaleDB service is fine on the free/trial plan).
3. Copy its connection string — it looks like
   `postgresql://tsdbadmin:PASSWORD@HOST.tsdb.cloud.timescale.com:PORT/tsdb?sslmode=require`.
   Keep this handy for step 3.

### 2. Push this Blueprint to Render

1. Go to [dashboard.render.com](https://dashboard.render.com), sign up if you haven't, and choose
   **New > Blueprint**.
2. Connect your GitHub account and pick the `iiot-device-monitor` repo. Render will detect
   `render.yaml` at the repo root and show the five services listed above.
3. Click **Apply** — Render will start building all five. This takes a few minutes the first time.

### 3. Add the one secret Render can't infer

`iiot-backend`'s `DATABASE_URL` is intentionally left blank in `render.yaml` (`sync: false`) — same
reason PMSDMS leaves its Neon connection string blank: it's a secret, not something to commit.

1. In Render's dashboard, open the `iiot-backend` service → **Environment**.
2. Paste your Timescale Cloud connection string from step 1 into `DATABASE_URL`.
3. Save — this triggers a redeploy of just that service.

### 4. Verify

Once all five services show "Live" in Render's dashboard, open `iiot-backend`'s URL (shown at the top
of its dashboard page, something like `https://iiot-backend-xxxx.onrender.com`). You should see the
same dashboard as local dev, with the two simulated devices streaming live data within a minute or two
(the edge gateway polls for its device config every 15s, same as local).

If it's not updating: check `iiot-edge-gateway`'s logs first (Render's dashboard → that service →
**Logs**) — most first-deploy issues are a service-to-service hostname not resolving yet, which
usually clears up on its own within a minute of all services finishing their first boot.

## Updating the deployment later

Render's Blueprint services auto-deploy on every push to `main` by default. Just `git push` as usual.
