import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'your_telegram_bot_token_here')
    
    # FFmpeg Configuration
    FFMPEG_BIN_PATH = os.getenv('FFMPEG_BIN_PATH', r'Q:\ffmpeg\bin')
    
    # Database Configuration
    DB_NAME = os.getenv('DB_NAME', 'database/smart_ecosystem.db')
    
    # Google APIs Configuration
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '')
    GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
    
    @property
    def GOOGLE_CREDENTIALS(self):
        """Get Google credentials from environment variable or file"""
        if self.GOOGLE_SERVICE_ACCOUNT_JSON:
            try:
                return json.loads(self.GOOGLE_SERVICE_ACCOUNT_JSON)
            except json.JSONDecodeError:
                print("Warning: Invalid JSON in GOOGLE_SERVICE_ACCOUNT_JSON")
                return None
        elif os.path.exists(self.GOOGLE_CREDENTIALS_PATH):
            with open(self.GOOGLE_CREDENTIALS_PATH, 'r') as f:
                return json.load(f)
        return None
    
    # Server Configuration
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8000))
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Base URL for email links
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
    
    # Timezone Configuration
    TIMEZONE = os.getenv('TIMEZONE', 'Africa/Cairo')
    
    # Email Configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    EMAIL_USER = os.getenv('EMAIL_USER', '')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
    
    # Google Gemini API Configuration
    GOOGLE_GEMINI_API_KEY = os.getenv('GOOGLE_GEMINI_API_KEY', '')
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')
    
    # Telegram API URL
    @property
    def TELEGRAM_API_URL(self):
        return f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage"

# Create config instance
config = Config()