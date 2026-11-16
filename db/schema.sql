-- Venture OS core schema: source registry (admin-managed) + two RAG indexes.
-- Postgres 16 + pgvector. Seeded once from config/sources/*.yaml by db/seed.py.
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- Roles: only admins may change the registry ----------
-- vos_admin : admin API connection; may INSERT/UPDATE/DELETE registry tables.
-- vos_agent : agents and crawler; READ registry, WRITE documents/chunks only.
-- vos_app   : founder-facing API; may file source requests, never edit the registry.
DO $$ BEGIN
  CREATE ROLE vos_admin NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE vos_agent NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE vos_app NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- vos_validator : the source validator; may only INSERT provisional, tier B/C sources (row-level policy below).
DO $$ BEGIN
  CREATE ROLE vos_validator NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------- Source registry ----------
CREATE TABLE IF NOT EXISTS sources (
  id               TEXT PRIMARY KEY,                -- R-001, CS-001, EG-001 ...
  scope            TEXT NOT NULL CHECK (scope IN ('global','region','country','industry')),
  source_name      TEXT NOT NULL,
  url              TEXT,
  domain           TEXT GENERATED ALWAYS AS (substring(url from '^https?://([^/]+)')) STORED,
  provides         TEXT,
  access_type      TEXT,                            -- API | download | manual | scrape
  auth_needed      TEXT,
  license          TEXT,
  coverage         TEXT,
  country_codes    TEXT[] DEFAULT '{}',             -- ISO 3166-1 alpha-2; empty = global
  industries       TEXT[] DEFAULT '{}',             -- ISIC sections; empty = all
  update_frequency TEXT,
  max_age_months   INT,
  tier             CHAR(1) NOT NULL CHECK (tier IN ('A','B','C')),
  crawl            TEXT NOT NULL DEFAULT 'full' CHECK (crawl IN ('full','metadata','none')),
  use              TEXT,                            -- market | analogy | ethics | legal ...
  active           BOOLEAN NOT NULL DEFAULT TRUE,   -- "remove" = deactivate; history kept
  verified         BOOLEAN NOT NULL DEFAULT FALSE,
  provisional      BOOLEAN NOT NULL DEFAULT FALSE,  -- auto-added by the validator, awaiting admin confirmation
  expires_at       TIMESTAMPTZ,                     -- provisional sources lapse unless an admin confirms them
  discovered_by    TEXT,                            -- run / discovery rule that found it
  url_status       TEXT, http_status INT, robots_ok BOOLEAN, license_detected TEXT,
  tested_on        DATE,
  notes            TEXT,
  created_by       TEXT NOT NULL,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (NOT provisional OR (tier IN ('B','C') AND expires_at IS NOT NULL))
);

-- Every admin change is recorded; the table is append-only.
CREATE TABLE IF NOT EXISTS source_changes (
  id         BIGSERIAL PRIMARY KEY,
  source_id  TEXT NOT NULL,
  action     TEXT NOT NULL CHECK (action IN ('add','update','deactivate','reactivate','auto_add','confirm','expire')),
  admin_id   TEXT NOT NULL,
  reason     TEXT NOT NULL,
  before     JSONB, after JSONB,
  at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sources proposed by crawler agents, with the validator's verdict on each check.
CREATE TABLE IF NOT EXISTS source_candidates (
  id            BIGSERIAL PRIMARY KEY,
  url           TEXT NOT NULL,
  source_name   TEXT,
  country_code  TEXT,
  kind          TEXT,                     -- statistics_office | central_bank | company_registry | regulator | other
  proposed_by   TEXT NOT NULL,            -- run id / agent id
  rationale     TEXT,
  found_via     TEXT,                     -- search query or discovery rule step
  checks        JSONB,                    -- {check_name: {passed: bool, detail: str}}
  verdict       TEXT NOT NULL DEFAULT 'pending' CHECK (verdict IN ('pending','rejected','provisional','queued')),
  source_id     TEXT,                     -- set when it became a provisional source
  decided_by    TEXT, decided_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Founders/agents can only *request* a domain; an admin approves or rejects it.
CREATE TABLE IF NOT EXISTS source_requests (
  id           BIGSERIAL PRIMARY KEY,
  url          TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  reason       TEXT,
  status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  decided_by   TEXT, decided_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS corpus_items (            -- methods & frameworks (corpus_seed.yaml)
  id TEXT PRIMARY KEY, title TEXT NOT NULL, author_publisher TEXT, url TEXT, year INT,
  type TEXT, topic TEXT, license TEXT, tier CHAR(1), how_we_use_it TEXT,
  status TEXT CHECK (status IN ('candidate','keep','maybe','cut')),
  created_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Technology catalog: models, tools, infrastructure ----------
CREATE TABLE IF NOT EXISTS components (
  id             TEXT PRIMARY KEY,                 -- T-001 ...
  kind           TEXT NOT NULL,                    -- model | embedding | reranker | inference | vector db | crawler | extraction | ...
  name           TEXT NOT NULL,
  url            TEXT,
  license        TEXT,                             -- as stated; '(verify)' = written from memory
  open_weight    BOOLEAN,                          -- models only: weights downloadable
  osi_open       BOOLEAN,                          -- licence is OSI-approved open source (NULL = unknown)
  use            TEXT,
  status         TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','selected','rejected')),
  active         BOOLEAN NOT NULL DEFAULT TRUE,
  verified_on    DATE,
  notes          TEXT,
  created_by     TEXT NOT NULL,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Which endpoint serves each model profile. Secrets are NEVER stored: only the NAME of the env var.
CREATE TABLE IF NOT EXISTS model_endpoints (
  id            TEXT PRIMARY KEY,                  -- E-001 ...
  profile       TEXT NOT NULL CHECK (profile IN ('reasoning','extract','code','judge','embed','rerank')),
  provider      TEXT NOT NULL CHECK (provider IN ('hosted','colab','local')),
  component_id  TEXT REFERENCES components(id),    -- the model family, when known
  base_url_env  TEXT,                              -- e.g. LLM_BASE_URL
  api_key_env   TEXT,                              -- e.g. LLM_API_KEY
  model_env     TEXT,                              -- env var holding the exact model id
  model_name    TEXT,                              -- or a fixed model id (local models)
  priority      INT NOT NULL DEFAULT 1,            -- 1 = tried first; higher = fallback
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  notes         TEXT,
  created_by    TEXT NOT NULL,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (api_key_env IS NULL OR api_key_env ~ '^[A-Z][A-Z0-9_]*$')
);

-- Admin changes to any catalog table (components, endpoints) are logged here.
CREATE TABLE IF NOT EXISTS catalog_changes (
  id         BIGSERIAL PRIMARY KEY,
  table_name TEXT NOT NULL,
  row_id     TEXT NOT NULL,
  action     TEXT NOT NULL CHECK (action IN ('add','update','deactivate','reactivate')),
  admin_id   TEXT NOT NULL,
  reason     TEXT NOT NULL,
  before     JSONB, after JSONB,
  at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Documents and chunks for BOTH RAG indexes ----------
-- index_name 'corpus' = stable methods/frameworks (ingested once, re-ingested on new edition)
-- index_name 'live'   = fresh market evidence fetched from registry sources
CREATE TABLE IF NOT EXISTS documents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  index_name    TEXT NOT NULL CHECK (index_name IN ('corpus','live')),
  source_id     TEXT REFERENCES sources(id),
  corpus_id     TEXT REFERENCES corpus_items(id),
  url           TEXT NOT NULL,
  title         TEXT,
  language      TEXT,
  published_at  DATE,                                -- from the page when available
  retrieved_at  TIMESTAMPTZ NOT NULL,
  content_hash  TEXT NOT NULL,
  valid_from    TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_to      TIMESTAMPTZ,                         -- set when a newer version replaces it
  license       TEXT,
  UNIQUE (url, content_hash)
);

CREATE TABLE IF NOT EXISTS chunks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  ordinal     INT NOT NULL,
  text        TEXT NOT NULL,
  tsv         TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,  -- keyword half of hybrid search
  embedding   VECTOR(1024)                                                      -- bge-m3 dimension
);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_emb_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- Freshness view: current documents with a STALE flag from the source's max_age_months.
CREATE OR REPLACE VIEW current_documents AS
SELECT d.*, s.tier, s.max_age_months,
       (s.max_age_months IS NOT NULL AND
        COALESCE(d.published_at, d.retrieved_at::date) < (now() - make_interval(months => s.max_age_months))::date) AS stale
FROM documents d LEFT JOIN sources s ON s.id = d.source_id
WHERE d.valid_to IS NULL AND (s.id IS NULL OR s.active);

-- ---------- Founder onboarding and briefs ----------
CREATE TABLE IF NOT EXISTS onboarding_sessions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  state       JSONB NOT NULL,                       -- OnboardingState: fields, messages, phase
  brief_id    UUID,                                 -- set once the founder confirms
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS founder_documents (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  UUID NOT NULL REFERENCES onboarding_sessions(id),
  filename    TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  size_bytes  INT NOT NULL,
  text        TEXT NOT NULL,                        -- extracted text only; the raw file is not kept
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS briefs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every change to a brief is a new version; stages pin the version they used.
CREATE TABLE IF NOT EXISTS brief_versions (
  brief_id    UUID NOT NULL REFERENCES briefs(id),
  version     INT NOT NULL,
  fields      JSONB NOT NULL,                       -- {field: {value, status, source, quote}}
  tags        JSONB NOT NULL DEFAULT '{}',          -- {industries, customer_type, revenue_model, country_code, languages}
  followups   JSONB NOT NULL DEFAULT '[]',          -- [{question, answer, source}]
  change_note TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (brief_id, version)
);
ALTER TABLE brief_versions ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '{}';
ALTER TABLE brief_versions ADD COLUMN IF NOT EXISTS followups JSONB NOT NULL DEFAULT '[]';
-- research questions found during onboarding, handed to Discover (not asked to the founder)
ALTER TABLE brief_versions ADD COLUMN IF NOT EXISTS open_questions JSONB NOT NULL DEFAULT '[]';

-- ---------- Row-level security on the registry ----------
-- Even a buggy validator cannot create an active, non-provisional or tier-A source.
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sources_read ON sources;
CREATE POLICY sources_read ON sources FOR SELECT USING (true);
DROP POLICY IF EXISTS sources_admin ON sources;
CREATE POLICY sources_admin ON sources FOR ALL TO vos_admin USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS sources_validator_insert ON sources;
CREATE POLICY sources_validator_insert ON sources FOR INSERT TO vos_validator
  WITH CHECK (provisional AND NOT verified AND tier IN ('B','C')
              AND expires_at IS NOT NULL AND expires_at <= now() + interval '31 days');

-- ---------- Grants ----------
GRANT SELECT ON sources, corpus_items, source_changes, current_documents TO vos_agent, vos_app;
GRANT SELECT, INSERT, UPDATE ON sources, corpus_items TO vos_admin;
GRANT SELECT, INSERT ON source_changes TO vos_admin;
GRANT SELECT, UPDATE ON source_requests TO vos_admin;
GRANT SELECT, INSERT ON source_requests TO vos_app, vos_agent;
GRANT SELECT, INSERT ON source_candidates TO vos_agent;
GRANT SELECT, UPDATE ON source_candidates TO vos_validator, vos_admin;
GRANT SELECT, INSERT ON sources TO vos_validator;
GRANT SELECT, INSERT ON source_changes TO vos_validator;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO vos_admin, vos_agent, vos_app, vos_validator;
GRANT SELECT, INSERT, UPDATE ON documents, chunks TO vos_agent;
GRANT SELECT ON documents, chunks TO vos_app, vos_admin;
GRANT SELECT ON components, model_endpoints, catalog_changes TO vos_agent, vos_app, vos_validator;
GRANT SELECT, INSERT, UPDATE ON components, model_endpoints TO vos_admin;
GRANT SELECT, INSERT ON catalog_changes TO vos_admin;
GRANT SELECT ON corpus_items, source_requests, source_candidates TO vos_admin;
GRANT SELECT, INSERT, UPDATE ON onboarding_sessions TO vos_app;
GRANT SELECT, INSERT ON founder_documents, briefs, brief_versions TO vos_app;
GRANT SELECT ON briefs, brief_versions TO vos_agent;
