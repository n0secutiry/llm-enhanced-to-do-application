from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str  # prod / dev
    LOG_FILE: str = "logs/app.log"
    MONGO_ROOT_USER: str
    MONGO_ROOT_PASSWORD: str
    MONGO_NAME_DB: str
    MONGO_HOST_DB: str
    MONGO_PORT_DB: int
    MONGO_TIMEOUT_SELECTION_SERVER_MS: int = 5000
    MONGO_TIMEOUT_CONNECT_MS: int = 3000
    EXCLUDE_PATHS: set = {"/docs", "/redoc", "/openapi.json"}

    OLLAMA_URL: str
    OLLAMA_MODEL: str
    OLLAMA_TIMEOUT_S: float = 30.0
    OLLAMA_INPUT_LIMIT: int = 2000

    # Prioritise a new todo in the background right after it is created
    AUTO_PRIORITIZE: bool = True

    # Priority formula weights: score = w1*urgency + w2*(6-effort) + w3*blocks
    PRIORITY_WEIGHT_URGENCY: float = 2.0
    PRIORITY_WEIGHT_EFFORT: float = 1.0
    PRIORITY_WEIGHT_BLOCKS: float = 1.5

    # Rate limit for LLM-backed endpoints
    LLM_RATE_LIMIT_REQUESTS: int = 10
    LLM_RATE_LIMIT_WINDOW_S: int = 60

    # LangFuse observability (optional: tracing is off while keys are empty)
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(
        extra="ignore", env_file=".env", env_ignore_empty=True
    )


settings = Settings()
