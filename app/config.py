from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str  # prod / dev
    MONGO_ROOT_USER: str
    MONGO_ROOT_PASSWORD: str
    MONGO_NAME_DB: str
    MONGO_HOST_DB: str
    MONGO_PORT_DB: int
    MONGO_TIMEOUT_SELECTION_SERVER_MS: int = 5000 
    MONGO_TIMEOUT_CONNECT_MS: int = 3000

    model_config = SettingsConfigDict(
        extra="ignore", env_file=".env", env_ignore_empty=True
    )


settings = Settings()
