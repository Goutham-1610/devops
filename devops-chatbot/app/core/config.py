from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Slack Configuration
    SLACK_SIGNING_SECRET: str
    SLACK_BOT_TOKEN: str
    
    # Application Settings  
    DEBUG: bool = False
    PORT: int = 8000
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    
    # MongoDB Configuration
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "devops_chatbot"
    
    # DevOps Settings
    DOCKER_HOST: str = "unix:///var/run/docker.sock"
    KUBERNETES_CONFIG_PATH: Optional[str] = None
    
    # Security Settings
    REQUEST_TIMEOUT: int = 300  # 5 minutes for Slack signature validation
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB max request size
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Bot Configuration
    BOT_NAME: str = "DevOps ChatBot"
    BOT_VERSION: str = "1.0.0"
    DEFAULT_RESPONSE_TIMEOUT: int = 30  # seconds
    
    # System Monitoring Settings
    METRICS_RETENTION_DAYS: int = 30
    HEALTH_CHECK_INTERVAL: int = 60  # seconds
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Validate required settings
        if not self.SLACK_SIGNING_SECRET:
            raise ValueError("SLACK_SIGNING_SECRET is required")
        if not self.SLACK_BOT_TOKEN:
            raise ValueError("SLACK_BOT_TOKEN is required")
        if not self.SLACK_BOT_TOKEN.startswith("xoxb-"):
            raise ValueError("SLACK_BOT_TOKEN must start with 'xoxb-'")
    
    @property
    def mongodb_connection_string(self) -> str:
        """Get formatted MongoDB connection string"""
        return f"{self.MONGODB_URL}/{self.MONGODB_DATABASE}"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.DEBUG
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return not self.DEBUG

# Global settings instance
settings = Settings()

# Validation function for startup
def validate_settings():
    """Validate critical settings on startup"""
    errors = []
    
    # Check Slack configuration
    if not settings.SLACK_SIGNING_SECRET:
        errors.append("SLACK_SIGNING_SECRET is missing")
    
    if not settings.SLACK_BOT_TOKEN:
        errors.append("SLACK_BOT_TOKEN is missing")
    elif not settings.SLACK_BOT_TOKEN.startswith("xoxb-"):
        errors.append("SLACK_BOT_TOKEN must start with 'xoxb-'")
    
    # Check MongoDB configuration
    if not settings.MONGODB_URL:
        errors.append("MONGODB_URL is missing")
    
    if not settings.MONGODB_DATABASE:
        errors.append("MONGODB_DATABASE is missing")
    
    # Check port availability
    if not (1024 <= settings.PORT <= 65535):
        errors.append(f"PORT {settings.PORT} is not in valid range (1024-65535)")
    
    if errors:
        raise ValueError(f"Configuration errors found:\n" + "\n".join(f"- {error}" for error in errors))
    
    return True

# Helper function to get environment info
def get_environment_info() -> dict:
    """Get current environment information"""
    return {
        "bot_name": settings.BOT_NAME,
        "version": settings.BOT_VERSION,
        "environment": "development" if settings.DEBUG else "production",
        "python_version": os.sys.version,
        "mongodb_database": settings.MONGODB_DATABASE,
        "port": settings.PORT,
        "log_level": settings.LOG_LEVEL
    }
