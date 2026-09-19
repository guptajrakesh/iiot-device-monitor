#!/bin/sh
# Generates a self-signed local CA + server certificate for the MQTT broker,
# so gateway<->broker<->backend traffic is encrypted even in local dev.
# Idempotent: skips generation if certs already exist in the shared volume.
set -e

CERT_DIR=/certs

if [ -f "$CERT_DIR/ca.crt" ] && [ -f "$CERT_DIR/server.crt" ]; then
  echo "Certs already present in $CERT_DIR - skipping generation."
  exit 0
fi

apk add --no-cache openssl >/dev/null

echo "Generating local CA + Mosquitto server certificate..."
openssl genrsa -out "$CERT_DIR/ca.key" 2048
openssl req -x509 -new -nodes -key "$CERT_DIR/ca.key" -sha256 -days 3650 \
  -subj "/CN=iiot-local-ca" -out "$CERT_DIR/ca.crt"

openssl genrsa -out "$CERT_DIR/server.key" 2048
openssl req -new -key "$CERT_DIR/server.key" -subj "/CN=mosquitto" -out "$CERT_DIR/server.csr"
openssl x509 -req -in "$CERT_DIR/server.csr" -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
  -CAcreateserial -out "$CERT_DIR/server.crt" -days 3650 -sha256

chmod 644 "$CERT_DIR"/*.crt "$CERT_DIR"/*.key
echo "Done - wrote ca.crt, server.crt, server.key to $CERT_DIR"
