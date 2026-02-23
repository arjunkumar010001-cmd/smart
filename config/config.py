import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    # SECURITY: Generate strong secrets using: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production-min32chars')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret-key-change-in-production-32ch')
    
    @classmethod
    def validate_production_secrets(cls):
        """Validate secrets in production - call this during app initialization"""
        env = os.getenv('FLASK_ENV', 'development')
        if env == 'production':
            if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 32 or 'dev-' in cls.SECRET_KEY:
                raise ValueError('SECRET_KEY must be set to a secure value (at least 32 characters) in production')
            if not cls.JWT_SECRET_KEY or len(cls.JWT_SECRET_KEY) < 32 or 'dev-' in cls.JWT_SECRET_KEY:
                raise ValueError('JWT_SECRET_KEY must be set to a secure value (at least 32 characters) in production')
    
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))
    
    # Database
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DB_NAME = os.getenv('DB_NAME', 'smart_hiring_db')
    
    # Email
    SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USER = os.getenv('SMTP_USER', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    
    # LinkedIn
    LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID', '')
    LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET', '')
    
    # Fairness thresholds
    DEMOGRAPHIC_PARITY_THRESHOLD = float(os.getenv('DEMOGRAPHIC_PARITY_THRESHOLD', 0.1))
    EQUAL_OPPORTUNITY_THRESHOLD = float(os.getenv('EQUAL_OPPORTUNITY_THRESHOLD', 0.1))
    
    # File upload
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads/resumes')
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}
    
    # Frontend
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    
    # AI Assessment APIs
    # Primary: Groq (FREE — LLaMA 3 / Mixtral, no credit card needed)
    # Get your free key at: https://console.groq.com/keys
    GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
    GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

    # Fallback 1: Anthropic Claude (PAID — only used if Groq fails)
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
    # Fallback 2: OpenAI GPT-4o-mini (PAID — only used if both above fail)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

    # Code Execution APIs
    # Primary: Piston API (FREE — no API key needed, 30+ languages)
    PISTON_API_URL = os.getenv('PISTON_API_URL', 'https://emkc.org/api/v2/piston')

    # Fallback: Judge0 Code Execution API (RapidAPI — 100 calls/day free)
    JUDGE0_API_URL = os.getenv('JUDGE0_API_URL', 'https://judge0-ce.p.rapidapi.com')
    JUDGE0_API_KEY = os.getenv('JUDGE0_API_KEY', '')
    JUDGE0_API_HOST = os.getenv('JUDGE0_API_HOST', 'judge0-ce.p.rapidapi.com')
    JUDGE0_SELF_HOSTED = os.getenv('JUDGE0_SELF_HOSTED', 'false')

    # API Cost Guards — daily call limits per provider
    GROQ_DAILY_LIMIT = int(os.getenv('GROQ_DAILY_LIMIT', '500'))
    CLAUDE_DAILY_LIMIT = int(os.getenv('CLAUDE_DAILY_LIMIT', '50'))
    OPENAI_DAILY_LIMIT = int(os.getenv('OPENAI_DAILY_LIMIT', '50'))

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    FLASK_ENV = 'development'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    FLASK_ENV = 'production'

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DB_NAME = 'smart_hiring_test_db'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
