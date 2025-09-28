#!/bin/bash
# Generate self-signed certificates for HTTPS development

CERT_DIR="certs"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"

# Create certs directory if it doesn't exist
mkdir -p $CERT_DIR

# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout $KEY_FILE \
    -out $CERT_FILE \
    -days 365 \
    -subj "/C=US/ST=State/L=City/O=MCP/CN=localhost" \
    -addext "subjectAltName = DNS:localhost,DNS:*.localhost,IP:127.0.0.1,IP:0.0.0.0"

echo "✅ Self-signed certificate generated:"
echo "   Certificate: $CERT_FILE"
echo "   Private Key: $KEY_FILE"
echo ""
echo "⚠️  This is a self-signed certificate for development only."
echo "   Clients will need to accept/trust this certificate."