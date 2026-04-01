-- Migration: Add must_change_password to users for forced password change on first login
-- Version: 0.6.0

-- UP MIGRATION
ALTER TABLE users
    ADD COLUMN must_change_password boolean NOT NULL DEFAULT false;

-- DOWN MIGRATION
ALTER TABLE users DROP COLUMN IF EXISTS must_change_password;
