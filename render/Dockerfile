# Single-container deployment for Render's free plan (see DEPLOY.md).
# Build context is the repo root (dockerContext: . in render.yaml) since this
# needs to pull from backend/, edge-gateway/, simulators/, and mosquitto/.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends mosquitto \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend-requirements.txt
COPY edge-gateway/requirements.txt gateway-requirements.txt
COPY simulators/modbus_sim/requirements.txt modbus-sim-requirements.txt
COPY simulators/opcua_sim/requirements.txt opcua-sim-requirements.txt
RUN pip install --no-cache-dir \
    -r backend-requirements.txt \
    -r gateway-requirements.txt \
    -r modbus-sim-requirements.txt \
    -r opcua-sim-requirements.txt

COPY backend/app ./backend/app
COPY edge-gateway/gateway ./edge-gateway/gateway
COPY simulators/modbus_sim/simulator.py ./simulators/modbus_sim/simulator.py
COPY simulators/opcua_sim/simulator.py ./simulators/opcua_sim/simulator.py
COPY mosquitto/config/mosquitto.cloud.conf /app/mosquitto.conf

COPY render/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV MQTT_HOST=localhost \
    MQTT_PORT=1883 \
    MODBUS_SIM_HOST=localhost \
    OPCUA_SIM_HOST=localhost \
    BACKEND_HOST=localhost \
    GATEWAY_ID=edge-gateway-1

CMD ["/entrypoint.sh"]
