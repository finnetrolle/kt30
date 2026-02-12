"""
Configuration module for the Technical Specification Analyzer application.
"""
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


class Config:
    """Application configuration class."""
    
    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # OpenAI API configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
    
    # Set to True if using OpenAI API (supports json_object response format)
    # Set to False if using other LLM APIs (like local LLM servers)
    OPENAI_JSON_MODE = os.getenv('OPENAI_JSON_MODE', 'true').lower() == 'true'
    
    # File upload configuration
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB default
    ALLOWED_EXTENSIONS = {'doc', 'docx'}
    
    # WBS template configuration
    WBS_TEMPLATE_PATH = os.getenv('WBS_TEMPLATE_PATH', 'wbs_template.md')
    
    @staticmethod
    def init_app():
        """Initialize application configuration."""
        logger.info("Initializing application configuration...")
        
        # Log configuration values (masking sensitive data)
        logger.info("Configuration values:")
        logger.info(f"  - DEBUG: {Config.DEBUG}")
        logger.info(f"  - OPENAI_API_BASE: {Config.OPENAI_API_BASE}")
        logger.info(f"  - OPENAI_MODEL: {Config.OPENAI_MODEL}")
        logger.info(f"  - OPENAI_JSON_MODE: {Config.OPENAI_JSON_MODE}")
        logger.info(f"  - UPLOAD_FOLDER: {Config.UPLOAD_FOLDER}")
        logger.info(f"  - MAX_CONTENT_LENGTH: {Config.MAX_CONTENT_LENGTH} bytes")
        logger.info(f"  - WBS_TEMPLATE_PATH: {Config.WBS_TEMPLATE_PATH}")
        
        # Check if API key is set
        if Config.OPENAI_API_KEY:
            masked_key = Config.OPENAI_API_KEY[:8] + "..." + Config.OPENAI_API_KEY[-4:] if len(Config.OPENAI_API_KEY) > 12 else "***"
            logger.info(f"  - OPENAI_API_KEY: {masked_key} (configured)")
        else:
            logger.warning("  - OPENAI_API_KEY: NOT SET! Application will not work without API key.")
        
        # Create upload folder if it doesn't exist
        if not os.path.exists(Config.UPLOAD_FOLDER):
            logger.info(f"Creating upload folder: {Config.UPLOAD_FOLDER}")
            os.makedirs(Config.UPLOAD_FOLDER)
            logger.info("Upload folder created")
        else:
            logger.info(f"Upload folder exists: {Config.UPLOAD_FOLDER}")
        
        logger.info("Configuration initialization completed")
    
    @staticmethod
    def allowed_file(filename: str) -> bool:
        """Check if the file extension is allowed.
        
        Args:
            filename: Name of the file to check
            
        Returns:
            True if file extension is allowed, False otherwise
        """
        if '.' not in filename:
            return False
        extension = filename.rsplit('.', 1)[1].lower()
        is_allowed = extension in Config.ALLOWED_EXTENSIONS
        logger.debug(f"File extension check: {extension} -> {'allowed' if is_allowed else 'not allowed'}")
        return is_allowed


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    TESTING = True


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
