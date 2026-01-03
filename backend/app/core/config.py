from typing import List
import os


class Settings:
    """Application settings loaded from environment variables."""
    
    def __init__(self):
        # Clerk Authentication
        self.CLERK_FRONTEND_API = os.getenv("CLERK_FRONTEND_API", "")
        if not self.CLERK_FRONTEND_API:
            raise ValueError("CLERK_FRONTEND_API environment variable is required")
        
        # CORS
        self.ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
        
        # DynamoDB
        self.DYNAMODB_ENABLED = os.getenv("DYNAMODB_TABLE_NAME") is not None
        self.DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
        self.AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
        
        # Storage
        self.NOTEBOOK_STORAGE_DIR = os.getenv("NOTEBOOK_STORAGE_DIR", "backend/data/notebooks")
        
        # Application
        self.APP_TITLE = "Reactive Notebook"
        self.DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    @property
    def jwks_url(self) -> str:
        return f"https://{self.CLERK_FRONTEND_API}/.well-known/jwks.json"


settings = Settings()

