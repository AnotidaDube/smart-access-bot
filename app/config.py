import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Smart Access WhatsApp Payment System"
    DEBUG: bool = False
    
    # Database Settings
    DATABASE_URL: str
    
    # Green API Settings
    GREEN_API_INSTANCE_ID: str
    GREEN_API_TOKEN: str
    
    # Access Corporation Meter API Settings
    METER_API_BASE_URL: str
    METER_API_APP_ID: str
    METER_API_APP_SECRET: str
    
    # Configuration to read the .env file
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate settings to be imported across the app
settings = Settings()