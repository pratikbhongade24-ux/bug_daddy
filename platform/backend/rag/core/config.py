import os

RAG_DATABASE_URL = os.getenv(
    "RAG_DATABASE_URL",
    "postgresql+psycopg2://sonar:change-me@bugdaddy-sonarqube-postgres.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com:5432/sonarqube",
)
RAG_REDIS_URL = os.getenv("RAG_REDIS_URL", "redis://localhost:6379/1")
RAG_WIDGET_API_KEY = os.getenv("RAG_WIDGET_API_KEY", "change-widget-key")
RAG_ADMIN_API_KEY = os.getenv("RAG_ADMIN_API_KEY", "change-admin-key")

BEDROCK_EMBEDDING_MODEL = os.getenv("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
BEDROCK_LLM_MODEL = os.getenv("BEDROCK_LLM_MODEL", "qwen.qwen3-coder-30b-a3b-v1:0")
USE_MOCK_BEDROCK = os.getenv("USE_MOCK_BEDROCK", "false").lower() == "true"

RETRIEVAL_TOP_K_VECTOR = int(os.getenv("RETRIEVAL_TOP_K_VECTOR", "15"))
RETRIEVAL_TOP_K_KEYWORD = int(os.getenv("RETRIEVAL_TOP_K_KEYWORD", "15"))
RETRIEVAL_TOP_K_MERGED = int(os.getenv("RETRIEVAL_TOP_K_MERGED", "12"))
RETRIEVAL_CONTEXT_CHARS = int(os.getenv("RETRIEVAL_CONTEXT_CHARS", "8000"))
RETRIEVAL_RRF_K = int(os.getenv("RETRIEVAL_RRF_K", "60"))
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.2"))
RETRIEVAL_MAX_PER_FILE = int(os.getenv("RETRIEVAL_MAX_PER_FILE", "3"))
MEMORY_MESSAGES = int(os.getenv("MEMORY_MESSAGES", "6"))
ENABLE_GROUNDED_FALLBACK = os.getenv("ENABLE_GROUNDED_FALLBACK", "true").lower() == "true"
RAG_APP_VERSION = os.getenv("RAG_APP_VERSION", "1.0.0")
RAG_APPLICATION_NAME = os.getenv("RAG_APPLICATION_NAME", "bank-loan-production-platform")
RAG_ENV = os.getenv("RAG_ENV", "production")
