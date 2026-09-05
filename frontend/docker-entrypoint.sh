#!/bin/sh
# Rewrites /usr/share/nginx/html/config.js from the API_BASE env var at
# container start, so the same built image can talk to any backend URL
# without rebuilding.
set -e

API_BASE="${API_BASE:-}"
cat > /usr/share/nginx/html/config.js <<EOF
window.__LG_API_BASE__ = "${API_BASE}";
EOF
