#!/bin/sh
# Writes /runtime-config.js from environment variables each time the container
# starts, so settings such as the Google Analytics id can change after
# deployment without rebuilding the image. Runs via the nginx image's
# /docker-entrypoint.d/ hook.
set -eu

TARGET=/usr/share/nginx/html/runtime-config.js
GA_ID="${GA_MEASUREMENT_ID:-}"

# Only a well-formed GA4 id is ever written (it ends up inside a script file).
case "$GA_ID" in
  G-*[!A-Z0-9]* | G-) GA_ID="" ;;
  G-*) ;;
  *) GA_ID="" ;;
esac

cat > "$TARGET" <<JS
window.__APP_CONFIG__ = { GA_MEASUREMENT_ID: '${GA_ID}' }
JS
echo "runtime-config.js written (GA_MEASUREMENT_ID=${GA_ID:-<empty>})"
