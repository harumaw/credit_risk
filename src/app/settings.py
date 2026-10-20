from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_DSN: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    class Config:
        env_file = "local.env"


settings = Settings()
