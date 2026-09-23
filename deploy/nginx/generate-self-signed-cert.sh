#!/bin/sh
# AquaResilience — quick local/demo HTTPS bootstrap (P5).
#
# Generates a throwaway self-signed certificate so the production compose
# stack (docker-compose.prod.yml) has *something* to bind to on port 443
# and comes up immediately — no domain, no DNS, no Let's Encrypt account
# needed. Browsers will show a "not trusted" warning for this cert; that is
# expected and fine for local testing or recording the demo video before a
# real domain is ready. It is NOT a substitute for a real certificate in an
# actual production deployment — see DEPLOYMENT.md for issuing a real one
# with certbot once a domain is available.
#
# Also doubles as the *bootstrap* cert for the real Let's Encrypt flow:
# nginx needs SOME cert file to exist at container start (its config always
# points at deploy/nginx/certs/fullchain.pem + privkey.pem, so the same
# nginx.conf.template works unmodified before and after switching to a real
# cert) — run this once, bring the stack up, then run certbot per
# DEPLOYMENT.md to replace these files with the real thing and reload nginx.
#
# Usage: ./generate-self-signed-cert.sh [domain]  (default: localhost)

set -eu

DOMAIN="${1:-localhost}"
CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/fullchain.pem" ] && [ -f "$CERT_DIR/privkey.pem" ]; then
    echo "Certs already exist at $CERT_DIR — leaving them as-is."
    echo "Delete $CERT_DIR/fullchain.pem and privkey.pem first if you want to regenerate."
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN"

chmod 644 "$CERT_DIR/fullchain.pem"
chmod 600 "$CERT_DIR/privkey.pem"

echo ""
echo "Self-signed certificate generated for '$DOMAIN' at:"
echo "  $CERT_DIR/fullchain.pem"
echo "  $CERT_DIR/privkey.pem"
echo ""
echo "This is NOT trusted by browsers — expect a security warning until it's"
echo "replaced with a real certificate (see DEPLOYMENT.md)."
