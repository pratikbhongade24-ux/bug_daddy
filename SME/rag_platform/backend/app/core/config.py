from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'SME RAG Platform'
    env: str = 'dev'
    log_level: str = 'INFO'

    database_url: str = 'postgresql+psycopg2://postgres:postgres@localhost:5432/app'
    redis_url: str = 'redis://localhost:6379/0'
    s3_bucket: str = 'sme-rag-documents'

    aws_region: str = 'us-east-1'
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_profile: str | None = None

    bedrock_embedding_model: str = 'amazon.titan-embed-text-v2:0'
    bedrock_llm_model: str = 'qwen.qwen3-coder-30b-a3b-v1:0'
    use_mock_bedrock: bool = False

    widget_api_key: str = 'change-widget-key'
    admin_api_key: str = 'change-admin-key'
    cors_allowed_origins: str = '*'
    retrieval_top_k_vector: int = 15
    retrieval_top_k_keyword: int = 15
    retrieval_top_k_merged: int = 12
    retrieval_context_chars: int = 8000
    retrieval_rrf_k: int = 60
    retrieval_min_score: float = 0.2
    retrieval_max_per_file: int = 3
    memory_messages: int = 6
    enable_query_rewrite: bool = True
    enable_grounded_fallback: bool = True

    app_version: str = '1.0.0'
    application_name: str = 'bank-loan-testing-platform'


settings = Settings()
