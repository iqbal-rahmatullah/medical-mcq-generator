from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "AQG Medis"
    environment: str = "local"
    RETRIEVER_CACHE_PATH: str = ".cache/retriever_cache.pkl"
    RETRIEVAL_MODE: str = "bm25_only"
    BM25_CANDIDATES_TOP_N: int = 200
    RERANK_TOP_N: int = 50
    EVIDENCE_TOP_K: int = 10
    EVIDENCE_TOP_K_EXPANDED: int = 20
    FUSION_ENABLED: bool = False
    RRF_K: int = 60
    LLM_PROVIDER: str = "gemini_sdk"
    LLM_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    CEREBRAS_API_KEY: str = ""
    LLM_API_BASE: str = "https://generativelanguage.googleapis.com/v1beta"
    LLM_MODEL: str = "gemini-2.5-flash-lite"
    LLM_TIMEOUT_SEC: float = 60.0
    LLM_TEMPERATURE: float = 0.2
    LLM_TOP_P: float = 1.0
    LLM_MAX_COMPLETION_TOKENS: int = 2048
    LLM_FALLBACKS: str = ""
    LLM_JSON_MODE: bool = True
    LLM_MAX_ATTEMPTS: int = 4
    LLM_CANDIDATES: int = 1
    LLM_DEDUP_ATTEMPTS: int = 2
    LLM_REASONING_EFFORT: str = ""
    LLM_STOP: str = ""
    LLM_STREAM: bool = False
    CEREBRAS_TIMEOUT_SEC: float = 30.0
    CEREBRAS_MAX_RETRIES: int = 1
    OK_ONLY_MODE: bool = True
    OK_ONLY_MAX_ROUNDS: int = 3
    OK_ONLY_MAX_SECONDS: float = 90.0
    EVIDENCE_FIRST: bool = True
    EVIDENCE_FIRST_MAX_SENTENCES: int = 2
    EVIDENCE_FIRST_MAX_CHARS: int = 600
    EVIDENCE_MAX_CHARS_PER_DOC: int = 800
    EVIDENCE_MAX_TOTAL_CHARS: int = 4000
    QUESTION_BANK_PATH: str = "app/logging/question_bank.jsonl"
    QUESTION_BANK_FALLBACK: bool = True
    QUESTION_BANK_WRITE_OK: bool = True
    QUESTION_BANK_ALLOW_ANY_TOPIC: bool = False
    REVIEWER_PROVIDER: str = ""
    REVIEWER_API_KEY: str = ""
    REVIEWER_API_BASE: str = ""
    REVIEWER_MODEL: str = ""
    REVIEWER_TIMEOUT_SEC: float = 60.0
    REVIEWER_FALLBACKS: str = ""
    REVIEWER_MAX_COMPLETION_TOKENS: int = 256
    
    # Cross-CoVe: 3 different reviewers for majority voting
    COVE_ENABLED: bool = True
    COVE_VOTE_COUNT: int = 3
    
    # Reviewer 1 config
    REVIEWER_1_PROVIDER: str = ""
    REVIEWER_1_API_KEY: str = ""
    REVIEWER_1_API_BASE: str = ""
    REVIEWER_1_MODEL: str = ""
    REVIEWER_1_FALLBACKS: str = ""
    
    # Reviewer 2 config
    REVIEWER_2_PROVIDER: str = ""
    REVIEWER_2_API_KEY: str = ""
    REVIEWER_2_API_BASE: str = ""
    REVIEWER_2_MODEL: str = ""
    REVIEWER_2_FALLBACKS: str = ""
    
    # Reviewer 3 config
    REVIEWER_3_PROVIDER: str = ""
    REVIEWER_3_API_KEY: str = ""
    REVIEWER_3_API_BASE: str = ""
    REVIEWER_3_MODEL: str = ""
    REVIEWER_3_FALLBACKS: str = ""
    CORPUS_PUBMED_HF_DATASET: str = "MedRAG/pubmed"
    CORPUS_TEXTBOOKS_HF_DATASET: str = "MedRAG/textbooks"
    CORPUS_HF_LOCAL_ONLY: bool = True
    CORPUS_HF_STREAMING: bool = True
    CORPUS_PUBMED_MAX_DOCS: int = 2000
    CORPUS_TEXTBOOKS_MAX_DOCS: int = 0
    PUBMED_WEB_ENABLED: bool = False
    PUBMED_WEB_MAX_RESULTS: int = 10
    PUBMED_WEB_TIMEOUT_SEC: float = 10.0
    PUBMED_API_KEY: str = ""
    PUBMED_EMAIL: str = ""
    NLI_MODEL: str = "pritamdeka/PubMedBERT-MNLI-MedNLI"
    SEMANTIC_MODEL: str = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"


settings = Settings()
