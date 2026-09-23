#!/bin/sh
# Runs INSIDE the certbot container (via --deploy-hook) right after a
# successful certificate issuance or renewal. Certbot's own certs live
# under /etc/letsencrypt/live/$DOMAIN/ (its normal layout, left untouched
# so `certbot renew` keeps tracking things correctly) — this copies the
# current cert into the flat /etc/nginx/certs/{fullchain,privkey}.pem path
# nginx.conf.template actually reads, which is bind-mounted into both this
# container and the reverse-proxy container (see docker-compose.prod.yml).
#
# nginx does NOT auto-reload on a changed cert file. After a renewal, run
# (from the host, or a cron entry — see DEPLOYMENT.md):
#   docker compose -f docker-compose.prod.yml exec reverse-proxy nginx -s reload
set -eu

if [ -z "${RENEWED_LINEAGE:-}" ]; then
    echo "certbot-deploy-hook.sh: RENEWED_LINEAGE not set, nothing to copy." >&2
    exit 1
fi

cp "$RENEWED_LINEAGE/fullchain.pem" /etc/nginx/certs/fullchain.pem
cp "$RENEWED_LINEAGE/privkey.pem" /etc/nginx/certs/privkey.pem
echo "Copied renewed certificate from $RENEWED_LINEAGE to /etc/nginx/certs/."
echo "Remember to reload nginx: docker compose -f docker-compose.prod.yml exec reverse-proxy nginx -s reload"
