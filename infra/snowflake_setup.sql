-- Run this in a Snowflake Worksheet (Worksheets tab in the UI)
-- This creates the database, tables, and a read-only role for the app

-- step 1: create a virtual warehouse (the compute engine)
-- X-SMALL is fine for a POC - it's the cheapest option
CREATE WAREHOUSE IF NOT EXISTS CC_BOT_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60        -- suspends after 60 seconds of no activity (saves credits)
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;

-- step 2: create the database and schema
CREATE DATABASE IF NOT EXISTS CC_ANALYTICS;
USE DATABASE CC_ANALYTICS;
CREATE SCHEMA IF NOT EXISTS JANUARY;
USE SCHEMA JANUARY;

-- step 3: create the three tables matching the CSV column names exactly
-- the app connects to these and loads them into in-memory SQLite at startup

CREATE TABLE IF NOT EXISTS ESTATE (
    "Interval"          TEXT,
    "All Ans"           FLOAT,
    "All Aband"         FLOAT,
    "All Ans %"         FLOAT,
    "Aband %"           FLOAT,
    "All Talk"          FLOAT,
    "Avg Talk"          FLOAT,
    "All ACW"           FLOAT,
    "Avg ACW"           FLOAT,
    "All Wait"          FLOAT,
    "Avg Wait"          FLOAT,
    "All Handling"      FLOAT,
    "Avg Handling"      FLOAT,
    "Max Wait"          FLOAT,
    "Ans 15"            FLOAT,
    "Ans 15 %"          FLOAT,
    "All In"            FLOAT,
    "dt"                TIMESTAMP_NTZ,
    "date"              DATE,
    "hour"              INTEGER,
    "weekday"           TEXT,
    "is_biz_hours"      BOOLEAN
);

CREATE TABLE IF NOT EXISTS QUEUES (
    "Interval"          TEXT,
    "Queue Name"        TEXT,
    "All Ans"           FLOAT,
    "All Aband"         FLOAT,
    "Aband %"           FLOAT,
    "Avg Wait"          FLOAT,
    "Max Wait"          FLOAT,
    "Ans 15"            FLOAT,
    "Ans 15 %"          FLOAT,
    "All Talk"          FLOAT,
    "Avg Talk"          FLOAT,
    "dt"                TIMESTAMP_NTZ,
    "date"              DATE,
    "hour"              INTEGER,
    "weekday"           TEXT,
    "is_biz_hours"      BOOLEAN
);

CREATE TABLE IF NOT EXISTS AGENTS (
    "Interval"          TEXT,
    "Agent Name"        TEXT,
    "In Ans"            FLOAT,
    "Out Ans"           FLOAT,
    "In Aband"          FLOAT,
    "In Aband %"        FLOAT,
    "In Talk"           FLOAT,
    "Avg In Talk"       FLOAT,
    "Out Talk"          FLOAT,
    "ACW"               FLOAT,
    "Avg ACW"           FLOAT,
    "dt"                TIMESTAMP_NTZ,
    "date"              DATE,
    "hour"              INTEGER,
    "weekday"           TEXT,
    "is_biz_hours"      BOOLEAN
);

-- step 4: create a read-only role for the app
-- the app only needs to SELECT, never INSERT/UPDATE/DELETE
CREATE ROLE IF NOT EXISTS CC_BOT_READ;

GRANT USAGE ON WAREHOUSE CC_BOT_WH TO ROLE CC_BOT_READ;
GRANT USAGE ON DATABASE CC_ANALYTICS TO ROLE CC_BOT_READ;
GRANT USAGE ON SCHEMA CC_ANALYTICS.JANUARY TO ROLE CC_BOT_READ;
GRANT SELECT ON ALL TABLES IN SCHEMA CC_ANALYTICS.JANUARY TO ROLE CC_BOT_READ;

-- to assign this role to your user, run:
-- GRANT ROLE CC_BOT_READ TO USER YOUR_USERNAME;
-- replace YOUR_USERNAME with your actual Snowflake username

-- verify everything looks right
SHOW TABLES IN SCHEMA CC_ANALYTICS.JANUARY;
