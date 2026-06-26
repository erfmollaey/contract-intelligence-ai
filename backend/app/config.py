from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Contract Intelligence"
    DATABASE_URL: str

    AI_BASE_URL: str
    AI_API_KEY: str
    AI_MODEL_NAME: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
