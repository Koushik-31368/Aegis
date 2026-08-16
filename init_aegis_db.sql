-- Run this as the postgres superuser after initdb to set up the aegis database.
-- Usage: psql -U postgres -f init_aegis_db.sql

-- Create the application role
CREATE USER aegis WITH PASSWORD 'aegis_dev';

-- Create the database owned by that role
CREATE DATABASE aegis OWNER aegis;

-- Grant all privileges on the new database
GRANT ALL PRIVILEGES ON DATABASE aegis TO aegis;

-- Connect to aegis and grant schema permissions
\connect aegis

GRANT ALL ON SCHEMA public TO aegis;
