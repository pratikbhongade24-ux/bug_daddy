CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_embeddings (
  id BIGSERIAL PRIMARY KEY,
  chunk_id VARCHAR(80) UNIQUE NOT NULL,
  content TEXT NOT NULL,
  content_tsv TEXT,
  embedding vector(1024) NOT NULL,
  metadata JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_conversations (
  id BIGSERIAL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  external_user_id VARCHAR(120) NOT NULL,
  session_id VARCHAR(120) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_messages (
  id BIGSERIAL PRIMARY KEY,
  conversation_id BIGINT NOT NULL REFERENCES rag_conversations(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL,
  content TEXT NOT NULL,
  tokens_in INTEGER,
  tokens_out INTEGER,
  latency_ms INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_citations (
  id BIGSERIAL PRIMARY KEY,
  message_id BIGINT NOT NULL REFERENCES rag_messages(id) ON DELETE CASCADE,
  chunk_id VARCHAR(80) NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  source_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(1000),
  metadata JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_feedback (
  id BIGSERIAL PRIMARY KEY,
  message_id BIGINT NOT NULL REFERENCES rag_messages(id) ON DELETE CASCADE,
  rating INTEGER NOT NULL,
  comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_audit_logs (
  id BIGSERIAL PRIMARY KEY,
  external_user_id VARCHAR(120),
  action VARCHAR(120) NOT NULL,
  status VARCHAR(30) NOT NULL,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_ingestion_jobs (
  id BIGSERIAL PRIMARY KEY,
  source VARCHAR(120) NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'PENDING',
  document_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_rag_embeddings_vector ON rag_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS ix_rag_embeddings_metadata_gin ON rag_embeddings USING gin (metadata);
CREATE INDEX IF NOT EXISTS ix_rag_conversations_user_session ON rag_conversations(external_user_id, session_id);
CREATE INDEX IF NOT EXISTS ix_rag_messages_conversation_id ON rag_messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_rag_citations_message_id ON rag_citations(message_id);
CREATE INDEX IF NOT EXISTS ix_rag_feedback_message_id ON rag_feedback(message_id);
CREATE INDEX IF NOT EXISTS ix_rag_audit_logs_created_at ON rag_audit_logs(created_at);
