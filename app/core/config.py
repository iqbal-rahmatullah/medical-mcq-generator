from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    project_name: str = "AQG Medis"
    environment: str = "local"
    RETRIEVAL_MODE: str = "bm25_only"
    BM25_CANDIDATES_TOP_N: int = 200
    RERANK_TOP_N: int = 50
    EVIDENCE_TOP_K: int = 20


settings = Settings()
