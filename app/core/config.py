from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    project_name: str = "AQG Medis"
    environment: str = "local"
    RETRIEVAL_MODE: str = "bm25_only"
    BM25_CANDIDATES_TOP_N: int = 200
    RERANK_TOP_N: int = 50
    EVIDENCE_TOP_K: int = 5
    FUSION_ENABLED: bool = False
    RRF_K: int = 60
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://generativelanguage.googleapis.com/v1beta"
    LLM_MODEL: str = "gemini-2.5-flash-lite"
    LLM_TIMEOUT_SEC: float = 60.0
    CORPUS_PUBMED_HF_DATASET: str = "MedRAG/pubmed"
    CORPUS_TEXTBOOKS_HF_DATASET: str = "MedRAG/textbooks"
    CORPUS_HF_LOCAL_ONLY: bool = True
    CORPUS_HF_STREAMING: bool = True
    CORPUS_PUBMED_MAX_DOCS: int = 2000
    CORPUS_TEXTBOOKS_MAX_DOCS: int = 0


settings = Settings()
