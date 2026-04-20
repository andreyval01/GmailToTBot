#!/bin/sh
set -eu

mkdir -p /data
chown -R appuser:appuser /data
exec runuser -u appuser -- python -m app.main
