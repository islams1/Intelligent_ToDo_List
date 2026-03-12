import os
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
    GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
    
    # Server Configuration
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8000))
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Timezone Configuration
    TIMEZONE = os.getenv('TIMEZONE', 'Africa/Cairo')
    
    # Email Configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    EMAIL_USER = os.getenv('EMAIL_USER', '')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
    
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