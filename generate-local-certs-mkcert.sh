#!/bin/bash
# Generate trusted local certificates using mkcert

echo "Checking if mkcert is installed..."

if ! command -v mkcert &> /dev/null; then
    echo "❌ mkcert is not installed."
    echo ""
    echo "Install mkcert:"
    echo "  macOS:   brew install mkcert"
    echo "  Linux:   https://github.com/FiloSottile/mkcert#installation"
    echo "  Windows: choco install mkcert"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "✅ mkcert found"
echo ""
echo "Installing local CA (you may be prompted for your password)..."
mkcert -install

echo ""
echo "Generating certificates for localhost..."
mkdir -p ./certs
cd ./certs
mkcert -cert-file server.crt -key-file server.key localhost 127.0.0.1 ::1

echo ""
echo "✅ Certificates generated in ./certs/"
echo "   - server.crt (certificate)"
echo "   - server.key (private key)"
echo ""
echo "🔒 Certificates are now trusted by your system!"
echo ""
echo "📝 To use with Docker:"
echo "   docker compose restart"
echo ""
echo "🌐 MCP Server URL: https://localhost:3001"
