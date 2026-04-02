-- Migration: Add must_change_password to users for forced password change on first login
-- Version: 0.0.1

-- UP MIGRATION
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT false;

-- DOWN MIGRATION
ALTER TABLE users DROP COLUMN IF EXISTS must_change_password;
