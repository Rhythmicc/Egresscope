#!/bin/sh
# Egresscope mihomo entrypoint: prefer the panel-staged kernel binary
# (/etc/mihomo/bin/mihomo-current) and fall back to the baked image binary.
set -e

CURRENT=/etc/mihomo/bin/mihomo-current
if [ -x "$CURRENT" ]; then
  exec "$CURRENT" -d /etc/mihomo -f /etc/mihomo/config.yaml
fi
exec /usr/local/bin/mihomo -d /etc/mihomo -f /etc/mihomo/config.yaml
