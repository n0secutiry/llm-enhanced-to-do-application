from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_ROOT_USER: str
    MONGO_ROOT_PASSWORD: str
    MONGO_NAME_DB: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()