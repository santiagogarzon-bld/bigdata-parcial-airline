#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?Set DATABASE_URL to the private RDS PostgreSQL endpoint (do not commit it)}"
case "${DATABASE_URL}" in
  postgresql://*|postgresql+psycopg://*) : ;;
  *) echo 'DATABASE_URL must use PostgreSQL' >&2; exit 2 ;;
esac
python -m airline_core.persistence.bootstrap --with-demo-data
