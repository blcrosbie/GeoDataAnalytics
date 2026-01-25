BEGIN;

-- Analytics schema for user contributions and data usage
CREATE SCHEMA IF NOT EXISTS analytics;

-- Users table for contributor management
CREATE TABLE IF NOT EXISTS analytics.users (
    id                             BIGSERIAL PRIMARY KEY,
    username                       VARCHAR(64) UNIQUE NOT NULL,
    email                          VARCHAR(255) UNIQUE NOT NULL,
    display_name                   VARCHAR(128),
    reputation_points              INTEGER DEFAULT 0,
    contribution_count             INTEGER DEFAULT 0,
    api_key_hash                   VARCHAR(255),
    is_active                      BOOLEAN DEFAULT TRUE,
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    last_login                     TIMESTAMPTZ,
    metadata                       JSONB
);

-- Data contributions tracking
CREATE TABLE IF NOT EXISTS analytics.contributions (
    id                             BIGSERIAL PRIMARY KEY,
    user_id                        BIGINT REFERENCES analytics.users(id),
    geoid                          VARCHAR(64) NOT NULL,
    year                           INTEGER NOT NULL,
    contribution_type              VARCHAR(32) NOT NULL, -- 'boundary', 'data', 'update'
    record_count                   INTEGER DEFAULT 1,
    attributes_added               TEXT[], -- array of attribute_keys added
    quality_score                  DECIMAL(3,2) DEFAULT 1.0, -- 0.0-1.0 rating
    batch_id                       UUID,
    source_file                    VARCHAR(255),
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    metadata                       JSONB
);

-- Data usage/queries tracking
CREATE TABLE IF NOT EXISTS analytics.data_queries (
    id                             BIGSERIAL PRIMARY KEY,
    user_id                        BIGINT REFERENCES analytics.users(id),
    geoid_pattern                  VARCHAR(128), -- pattern of geoids queried
    attribute_keys                 TEXT[], -- array of attributes accessed
    query_type                     VARCHAR(32), -- 'read', 'spatial', 'aggregate'
    result_count                   INTEGER,
    query_duration_ms              INTEGER,
    api_endpoint                   VARCHAR(128),
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    metadata                       JSONB
);

-- Monthly trending data points
CREATE TABLE IF NOT EXISTS analytics.trending_attributes (
    id                             BIGSERIAL PRIMARY KEY,
    year                           INTEGER NOT NULL,
    month                          INTEGER NOT NULL,
    attribute_key                  VARCHAR(128) NOT NULL,
    query_count                    INTEGER DEFAULT 0,
    unique_users                   INTEGER DEFAULT 0,
    contribution_count              INTEGER DEFAULT 0,
    trending_score                 DECIMAL(10,2) DEFAULT 0.0,
    created_at                     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(year, month, attribute_key)
);

-- User reputation events
CREATE TABLE IF NOT EXISTS analytics.reputation_events (
    id                             BIGSERIAL PRIMARY KEY,
    user_id                        BIGINT REFERENCES analytics.users(id),
    event_type                     VARCHAR(32) NOT NULL, -- 'contribution', 'quality_bonus', 'popular_data'
    points_awarded                 INTEGER NOT NULL,
    reason                         TEXT,
    reference_id                   BIGINT, -- links to contribution or query ID
    created_at                     TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for analytics tables
CREATE INDEX IF NOT EXISTS idx_contributions_user 
    ON analytics.contributions (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_contributions_geoid_year 
    ON analytics.contributions (geoid, year);

CREATE INDEX IF NOT EXISTS idx_data_queries_user 
    ON analytics.data_queries (user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_trending_attributes_score 
    ON analytics.trending_attributes (trending_score DESC, year, month);

CREATE INDEX IF NOT EXISTS idx_reputation_events_user 
    ON analytics.reputation_events (user_id, created_at);

-- Grant permissions to geoagent user
GRANT USAGE ON SCHEMA analytics TO geoagent;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA analytics TO geoagent;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA analytics TO geoagent;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT ALL ON TABLES TO geoagent;

COMMIT;