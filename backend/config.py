"""
Global Configuration Management
==============================
Centralizes all application environment variables and tuning parameters 
using Pydantic Settings for validation and default fallback.
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Core Infrastructure
    DATABASE_URL: str = "postgresql://admin:secret@localhost:5432/campushare"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security and Session Management
    JWT_SECRET: str = "change-this-secret"
    JWT_EXPIRY_HOURS: int = 24
    
    # File Storage and Execution Limits
    RESULTS_DIR: str = "./results"
    MAX_RETRY_COUNT: int = 3
    # Duration a job remains in 'pending' before being considered stale
    JOB_QUEUE_TIMEOUT_SECONDS: int = 1800
    
    # Grid Heartbeat and Synchronization
    SCHEDULER_TICK_SECONDS: int = 2
    # Threshold for considering a node 'offline' if no heartbeat is received
    HEARTBEAT_TTL_SECONDS: int = 600
    
    # Networking and Security

    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """
        Parses a comma-separated string of origins into a list for FastAPI CORS middleware.
        """
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        # Load environment overrides from a .env file if present
        env_file = ".env"
        # Ignore extra variables not explicitly defined in this schema
        extra = "ignore"


# Global singleton instance for use across the backend

settings = Settings()
