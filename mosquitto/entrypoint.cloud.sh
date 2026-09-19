#!/bin/sh
# Render's Web Service type requires an HTTP port to consider a service
# "live"; mosquitto itself only speaks MQTT, so run a trivial HTTP responder
# alongside it purely to satisfy that check (same reasoning as the
# _run_health_server() helper in the Python services).
set -e
python3 -m http.server "${PORT:-8080}" &
exec mosquitto -c /mosquitto/config/mosquitto.conf
