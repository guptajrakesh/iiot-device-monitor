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
# limited CPU during its own startup (DB connect/seed) - Render's health
# check has a limited grace period on first deploy, and starting backend
# last (after mosquitto + two simulators + the gateway all fight for the
# same CPU share) pushed it past that window on a real deploy.
#
# PORT (Render's assigned public port) must only ever be bound by the
# backend - the simulators/gateway each carry their own leftover
# health-check listener from the old multi-service design that otherwise
# defaults to the same $PORT and races the real backend for it.
set -e

echo "[entrypoint] starting backend..."
(cd /app/backend && exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT") &
BACKEND_PID=$!

echo "[entrypoint] starting mosquitto..."
mosquitto -c /app/mosquitto.conf &

echo "[entrypoint] starting Modbus simulator..."
(export PORT=18081; cd /app/simulators/modbus_sim && exec python simulator.py) &

echo "[entrypoint] starting OPC-UA simulator..."
(export PORT=18082; cd /app/simulators/opcua_sim && exec python simulator.py) &

sleep 2

echo "[entrypoint] starting edge gateway..."
(
  export BACKEND_PORT="$PORT"
  export PORT=18083
  cd /app/edge-gateway
  exec python -m gateway.main
) &

# Ties the container's lifecycle to the backend specifically - if it dies,
# the container exits so Render notices and restarts it.
wait "$BACKEND_PID"
