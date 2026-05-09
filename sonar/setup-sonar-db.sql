-- Optional PostgreSQL setup for an existing PostgreSQL instance.
-- The setup-aws.sh script creates a dedicated RDS PostgreSQL database with
-- the sonar user as master user, so this file is mainly for manual recovery
-- or migration scenarios.

CREATE DATABASE sonarqube;
CREATE USER sonar WITH PASSWORD 'replace-with-secure-password';
GRANT ALL PRIVILEGES ON DATABASE sonarqube TO sonar;

\connect sonarqube

CREATE SCHEMA IF NOT EXISTS public AUTHORIZATION sonar;
GRANT ALL ON SCHEMA public TO sonar;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO sonar;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO sonar;
