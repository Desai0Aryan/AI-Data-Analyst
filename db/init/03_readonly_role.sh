#!/bin/sh
# Creates the least-privilege role the API connects as.
# Defense in depth: even if the SQL guard were bypassed, this role cannot write.
set -eu          # POSIX sh: the postgres:alpine image has no bash

psql -v ON_ERROR_STOP=1 -v ro_password="${READONLY_PASSWORD}" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE analyst_ro LOGIN PASSWORD :'ro_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_ro;

ALTER ROLE analyst_ro SET default_transaction_read_only = on;
ALTER ROLE analyst_ro SET statement_timeout = '5s';
ALTER ROLE analyst_ro SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE analyst_ro CONNECTION LIMIT 20;
EOSQL
