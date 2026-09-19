# Deploying to Render (free tier)

This deploys the whole stack as **one** Render Web Service — backend, MQTT broker, both simulators,
and the edge gateway all run as sibling processes inside a single container, talking to each other over
`localhost` (see `render/entrypoint.sh`). It's backed by a free
[Timescale Cloud](https://console.cloud.timescale.com) database, same pattern as this org's other
project (a single web service + an external managed Postgres).

This single-container design isn't the original plan — it's the result of hitting three Render free-plan
limits in a row while deploying this for real: Private Services aren't available on the free plan,
neither are Background Workers, and (confirmed by an actual failed deploy) short internal hostnames
like `iiot-mosquitto` don't resolve between separate free-plan Web Services at all. Bundling everything
into one container sidesteps all three at once, since nothing needs to cross a service boundary.

**No credit card should be required for either signup**, based on current public info as of this
writing — Timescale Cloud's free trial/Beta plan explicitly doesn't ask for one, and Render's free
tier generally doesn't either. That said, **if either site asks you for card details at any point,
stop and don't enter them** — come back here and we'll figure out an alternative rather than proceed.

## What you'll end up with

One Render service, `iiot-device-monitor` (Web Service, Docker runtime) — its URL is the dashboard you
visit. The database lives outside Render entirely, on Timescale Cloud.

**Note on security**: MQTT never leaves the container in this design, so it's plaintext internally
(`mosquitto/config/mosquitto.cloud.conf`) rather than TLS-encrypted like local `docker compose up`'s
broker — there's no network hop between services here for TLS to protect. Separately, and more
importantly: **this app has no authentication anywhere**. The backend's URL, once deployed, is a normal
public web address with zero login — anyone who has the link can onboard/delete devices, read all data,
and change alert rules. Don't put anything sensitive behind it, and treat the link as effectively public.

## Steps

### 1. Create a free Timescale Cloud database

1. Go to [console.cloud.timescale.com](https://console.cloud.timescale.com) and sign up (email only).
2. Create a new service (the default Postgres + TimescaleDB service is fine on the free/trial plan).
3. Copy its connection string — it looks like
   `postgresql://tsdbadmin:PASSWORD@HOST.tsdb.cloud.timescale.com:PORT/tsdb?sslmode=require`.
   Keep this handy for step 3. **Change `postgres://` to `postgresql+psycopg2://`** — SQLAlchemy (which
   the backend uses) doesn't accept the shorter `postgres://` scheme some tools generate.

### 2. Push this Blueprint to Render

1. Go to [dashboard.render.com](https://dashboard.render.com), sign up if you haven't, and choose
   **New > Blueprint**.
2. Connect your GitHub account and pick the `iiot-device-monitor` repo (if it's not listed, its GitHub
   App installation likely needs to be given access to that repo specifically — GitHub → Settings →
   Applications → Installed GitHub Apps → Render → Configure → add the repo).
3. Render will detect `render.yaml` and show one service, `iiot-device-monitor`, plus a field for
   `DATABASE_URL`.
4. Paste your (corrected, `postgresql+psycopg2://`) Timescale Cloud connection string into that field.
5. Click **Deploy Blueprint**. The first build takes a few minutes (installing mosquitto plus every
   Python service's dependencies in one image).

### 3. Verify

Once it shows "Live", open its URL (shown at the top of the service's dashboard page, something like
`https://iiot-device-monitor-xxxx.onrender.com`). You should see the same dashboard as local dev, with
the two simulated devices streaming live data within a minute or so of the container finishing startup.

If it's not updating, check the service's **Logs** tab — the backend, gateway, and both simulators all
log to the same combined stream there, prefixed by their own logger names (`edge-gateway`, `modbus-sim`,
`opcua-sim`, `mqtt-ingest`, etc.), so it's usually clear which piece is complaining.

**Free-tier cold starts**: the instance spins down after ~15 minutes of no incoming HTTP requests, which
also pauses every process inside it (the simulators, the gateway, all of it) since they all share the
one container's lifecycle. Visiting the URL wakes it back up (can take 30-60s), and data resumes
shortly after. An external uptime pinger (e.g. a free [UptimeRobot](https://uptimerobot.com) check
hitting the URL every 10 minutes) is the usual free-tier workaround if you want it to stay warm.

## Updating the deployment later

Render's Blueprint services auto-deploy on every push to `main` by default. Just `git push` as usual.
