#!/bin/bash
# Generate self-signed certificates for local MCP development

CERT_DIR="./certs"
mkdir -p "$CERT_DIR"

echo "Generating self-signed certificate for localhost..."

# Generate private key
openssl genrsa -out "$CERT_DIR/server.key" 2048

# Generate certificate signing request
openssl req -new -key "$CERT_DIR/server.key" -out "$CERT_DIR/server.csr" \
  -subj "/C=US/ST=State/L=City/O=Development/CN=localhost"

# Generate self-signed certificate (valid for 365 days)
openssl x509 -req -days 365 \
  -in "$CERT_DIR/server.csr" \
  -signkey "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -extfile <(printf "subjectAltName=DNS:localhost,IP:127.0.0.1")

# Clean up CSR
rm "$CERT_DIR/server.csr"

echo ""
echo "✅ Certificates generated in $CERT_DIR/"
echo "   - server.crt (certificate)"
echo "   - server.key (private key)"
echo ""
echo "🔒 To use with Docker:"
echo "   docker compose up -d"
echo ""
echo "📝 MCP Server URL: https://localhost:3001"
echo ""
echo "⚠️  Note: You may need to accept the self-signed certificate in your browser/Claude Desktop"
