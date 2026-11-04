CREATE TABLE IF NOT EXISTS feedback (
 id BIGSERIAL PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
 product_query TEXT NOT NULL, text TEXT NOT NULL, text_hash TEXT NOT NULL,
 url TEXT, created_at TIMESTAMPTZ, engagement INTEGER DEFAULT 0,
 author_hash TEXT, collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 verification_status TEXT NOT NULL DEFAULT 'unknown',
 trust_score INTEGER NOT NULL DEFAULT 0 CHECK (trust_score BETWEEN 0 AND 100),
 verification_details JSONB NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE(source,source_id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_source ON feedback(source);
CREATE INDEX IF NOT EXISTS idx_feedback_product ON feedback(product_query);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC);
CREATE TABLE IF NOT EXISTS collection_tasks (
 id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, keywords TEXT[] NOT NULL,
 sources TEXT[] NOT NULL, mode TEXT NOT NULL DEFAULT 'demo',
 interval_seconds INTEGER NOT NULL DEFAULT 60, batch_size INTEGER NOT NULL DEFAULT 20,
 status TEXT NOT NULL DEFAULT 'running', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), last_run_at TIMESTAMPTZ,
 records_published BIGINT NOT NULL DEFAULT 0
);

-- Application accounts. The API seeds the initial demo administrator at startup.
CREATE TABLE IF NOT EXISTS app_users (
 id BIGSERIAL PRIMARY KEY,
 username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','user')),
 permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
