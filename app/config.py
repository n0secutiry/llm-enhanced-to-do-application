from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_ROOT_USER: str
    MONGO_ROOT_PASSWORD: str
    MONGO_NAME_DB: str
    MONGO_PORT_DB: int

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        env_ignore_empty=True
    )


settings = Settings()