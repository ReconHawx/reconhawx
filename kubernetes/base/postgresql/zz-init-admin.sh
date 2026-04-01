#!/bin/bash
set -e

USER_COUNT=$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc \
  "SELECT COUNT(*) FROM users;")

if [ "$USER_COUNT" -eq "0" ]; then
    ADMIN_PASSWORD=$(head -c 48 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 24)

    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        INSERT INTO users (id, username, password_hash, is_active, is_superuser, roles, created_at, updated_at, must_change_password)
        VALUES (
            gen_random_uuid(),
            'admin',
            crypt('$ADMIN_PASSWORD', gen_salt('bf', 12)),
            true,
            true,
            ARRAY['admin'],
            NOW(),
            NOW(),
            true
        );
EOSQL

    echo "========================================" >&2
    echo "  ADMIN USER CREATED"                    >&2
    echo "  Username: admin"                       >&2
    echo "  Password: $ADMIN_PASSWORD"             >&2
    echo "  ** Change this password after login **" >&2
    echo "========================================" >&2
else
    echo "Users table already has entries, skipping admin user creation." >&2
fi
