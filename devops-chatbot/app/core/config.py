from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    SLACK_SIGNING_SECRET: str
    SLACK_BOT_TOKEN: str
    DEBUG: bool = False
    PORT: int = 8000
    
    # MongoDB settings (instead of PostgreSQL)
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "devops_chatbot"
    
    class Config:
        env_file = ".env"

settings = Settings()
