#!/bin/sh
# Render's free plan only offers the Web Service type, and (confirmed via a
# live deploy) short internal hostnames like "iiot-mosquitto" don't resolve
# between separate Web Services on that plan - there's no usable private
# network here. Rather than fight that, this runs every component as a
# sibling process in ONE container, talking to each other over localhost.
# Only the backend's own HTTP/WebSocket API is exposed externally by Render;
# MQTT/Modbus/OPC-UA traffic never leaves the container.
#
# Backend starts FIRST, before anything else competes for the free tier's
# limited CPU during its own startup (DB connect/seed).
#
# Every background process runs inside a tiny restart loop: if any of them
# ever exits (crash, an uncaught exception, anything), nothing in a plain
# multi-process container would otherwise notice or restart it - backend
# would keep answering Render's health check just fine while, say, the
# gateway sat dead and no new data ever arrived again. This is what actually
# happened on a real deploy (traced to an uncaught asyncio.CancelledError in
# the gateway, now also fixed at the source in gateway/main.py) - this loop
# is the safety net for that failure mode and any other one like it.
set -e

echo "[entrypoint] starting backend..."
(cd /app/backend && exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT") &
BACKEND_PID=$!

run_forever() {
  name="$1"
  shift
  while true; do
    # "|| true" matters: under `set -e`, a non-zero exit from "$@" (the
    # crash this loop exists to recover from) would otherwise trigger
    # errexit and kill the loop itself before it can restart anything.
    "$@" || true
    echo "[entrypoint] $name exited unexpectedly - restarting in 2s" >&2
    sleep 2
  done
}

run_forever mosquitto mosquitto -c /app/mosquitto.conf &

run_forever modbus-sim sh -c 'export PORT=18081; cd /app/simulators/modbus_sim && python simulator.py' &

run_forever opcua-sim sh -c 'export PORT=18082; cd /app/simulators/opcua_sim && python simulator.py' &

sleep 2

run_forever edge-gateway sh -c "export BACKEND_PORT=\"$PORT\"; export PORT=18083; cd /app/edge-gateway && python -m gateway.main" &

# Ties the container's lifecycle to the backend specifically - if it dies,
# the container exits so Render notices and restarts it.
wait "$BACKEND_PID"
