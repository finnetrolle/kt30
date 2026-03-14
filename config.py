"""
Configuration module for the Technical Specification Analyzer application.
"""
import os
import logging
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


class StabilizationConfig:
    """Configuration for result stabilization."""
    
    # Available modes:
    # - single: Single pass, no stabilization (fastest, least stable)
    # - validate: Single pass with validation and normalization
    # - ensemble: Multiple passes with consensus (slowest, most stable)
    # - ensemble_validate: Ensemble + validation (recommended for production)
    MODE = os.getenv('STABILIZATION_MODE', 'validate')
    
    # Number of iterations for ensemble mode (3-5 recommended)
    ENSEMBLE_ITERATIONS = int(os.getenv('ENSEMBLE_ITERATIONS', '3'))
    
    # Consensus method: 'median', 'mean', 'trimmed_mean'
    CONSENSUS_METHOD = os.getenv('CONSENSUS_METHOD', 'median')
    
    # Outlier detection threshold (standard deviations)
    OUTLIER_THRESHOLD = float(os.getenv('OUTLIER_THRESHOLD', '2.0'))
    
    # Auto-normalize values to acceptable ranges
    AUTO_NORMALIZE = os.getenv('AUTO_NORMALIZE', 'true').lower() == 'true'
    
    # Apply validation rules
    APPLY_RULES_VALIDATION = os.getenv('APPLY_RULES_VALIDATION', 'true').lower() == 'true'
    
    # Minimum confidence score to accept result
    MIN_CONFIDENCE_SCORE = float(os.getenv('MIN_CONFIDENCE_SCORE', '0.7'))
    
    # Path to estimation rules file
    ESTIMATION_RULES_PATH = os.getenv('ESTIMATION_RULES_PATH', 'data/estimation_rules.json')


class Config:
    """Application configuration class."""

    ENV_NAME = os.getenv('APP_ENV', os.getenv('FLASK_ENV', 'development')).lower()

    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    TESTING = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = os.getenv(
        'SESSION_COOKIE_SECURE',
        'true' if ENV_NAME == 'production' else 'false'
    ).lower() == 'true'
    PERMANENT_SESSION_LIFETIME = timedelta(
        seconds=int(os.getenv('PERMANENT_SESSION_LIFETIME_SECONDS', str(12 * 60 * 60)))
    )

    # Authentication (optional — set APP_AUTH_PASSWORD to enable)
    APP_AUTH_PASSWORD = os.getenv('APP_AUTH_PASSWORD', '')
    
    # OpenAI API configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
    LLM_PROFILE = os.getenv('LLM_PROFILE', 'default').lower()
    SMALL_LLM_MODE = LLM_PROFILE == 'small'
    
    # Set to True if using OpenAI API (supports json_object response format)
    # Set to False if using other LLM APIs (like local LLM servers)
    OPENAI_JSON_MODE = os.getenv('OPENAI_JSON_MODE', 'true').lower() == 'true'
    DEFAULT_LLM_MAX_TOKENS = int(os.getenv('DEFAULT_LLM_MAX_TOKENS', '6000' if SMALL_LLM_MODE else '16000'))
    LLM_MAX_PARALLEL_REQUESTS = int(os.getenv('LLM_MAX_PARALLEL_REQUESTS', '2' if SMALL_LLM_MODE else '4'))
    ANALYSIS_CHUNK_CHARS = int(os.getenv('ANALYSIS_CHUNK_CHARS', '3500' if SMALL_LLM_MODE else '6000'))
    ANALYSIS_CHUNK_MAX_TOKENS = int(os.getenv('ANALYSIS_CHUNK_MAX_TOKENS', '1500' if SMALL_LLM_MODE else '3000'))
    ANALYSIS_SYNTHESIS_MAX_TOKENS = int(os.getenv('ANALYSIS_SYNTHESIS_MAX_TOKENS', '2500' if SMALL_LLM_MODE else '5000'))
    WBS_SKELETON_MAX_TOKENS = int(os.getenv('WBS_SKELETON_MAX_TOKENS', '2500' if SMALL_LLM_MODE else '5000'))
    WBS_TASKS_MAX_TOKENS = int(os.getenv('WBS_TASKS_MAX_TOKENS', '1400' if SMALL_LLM_MODE else '2500'))
    WBS_REFINEMENT_MAX_TOKENS = int(os.getenv('WBS_REFINEMENT_MAX_TOKENS', '2500' if SMALL_LLM_MODE else '5000'))
    VALIDATION_MAX_TOKENS = int(os.getenv('VALIDATION_MAX_TOKENS', '1500' if SMALL_LLM_MODE else '3000'))
    ENABLE_ANALYSIS_SYNTHESIS_LLM = os.getenv(
        'ENABLE_ANALYSIS_SYNTHESIS_LLM',
        'false' if SMALL_LLM_MODE else 'true'
    ).lower() == 'true'
    ENABLE_WBS_SKELETON_LLM = os.getenv(
        'ENABLE_WBS_SKELETON_LLM',
        'false' if SMALL_LLM_MODE else 'true'
    ).lower() == 'true'
    ENABLE_LLM_SEMANTIC_VALIDATION = os.getenv(
        'ENABLE_LLM_SEMANTIC_VALIDATION',
        'false' if SMALL_LLM_MODE else 'true'
    ).lower() == 'true'
    SMALL_LLM_ONLY_DEV_LLM_TASKS = os.getenv(
        'SMALL_LLM_ONLY_DEV_LLM_TASKS',
        'true' if SMALL_LLM_MODE else 'false'
    ).lower() == 'true'
    
    # File upload configuration
    RUNTIME_DIR = os.getenv('RUNTIME_DIR', 'runtime')
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
    ARTIFACTS_ROOT = os.getenv('ARTIFACTS_ROOT', 'analysis_runs')
    RESULTS_STORAGE_DIR = os.getenv('RESULTS_STORAGE_DIR', 'results_data')
    PROGRESS_STORAGE_DIR = os.getenv('PROGRESS_STORAGE_DIR', 'progress_data')
    JOB_QUEUE_DB_PATH = os.getenv('JOB_QUEUE_DB_PATH', os.path.join(RUNTIME_DIR, 'job_queue.sqlite3'))
    RATE_LIMIT_DB_PATH = os.getenv('RATE_LIMIT_DB_PATH', os.path.join(RUNTIME_DIR, 'rate_limits.sqlite3'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB default
    RESULT_TTL_SECONDS = int(os.getenv('RESULT_TTL_SECONDS', 24 * 60 * 60))
    PROGRESS_TTL_SECONDS = int(os.getenv('PROGRESS_TTL_SECONDS', 2 * 60 * 60))
    ARTIFACT_RETENTION_SECONDS = int(os.getenv('ARTIFACT_RETENTION_SECONDS', 7 * 24 * 60 * 60))
    JOB_RETENTION_SECONDS = int(os.getenv('JOB_RETENTION_SECONDS', 7 * 24 * 60 * 60))
    JOB_STALE_AFTER_SECONDS = int(os.getenv('JOB_STALE_AFTER_SECONDS', 30 * 60))
    WORKER_POLL_INTERVAL_SECONDS = float(os.getenv('WORKER_POLL_INTERVAL_SECONDS', '2.0'))
    EMBEDDED_WORKER_ENABLED = os.getenv(
        'EMBEDDED_WORKER_ENABLED',
        'true' if ENV_NAME == 'development' else 'false'
    ).lower() == 'true'
    # Note: .doc (legacy Word format) is NOT supported by python-docx, only .docx
    ALLOWED_EXTENSIONS = {'docx', 'pdf'}
    
    # WBS template configuration
    WBS_TEMPLATE_PATH = os.getenv('WBS_TEMPLATE_PATH', 'wbs_template.md')
    
    # Stabilization configuration
    STABILIZATION_MODE = StabilizationConfig.MODE
    ENSEMBLE_ITERATIONS = StabilizationConfig.ENSEMBLE_ITERATIONS
    ESTIMATION_RULES_PATH = StabilizationConfig.ESTIMATION_RULES_PATH
    
    @classmethod
    def apply_runtime_overrides(cls, source_cls: type) -> None:
        """Reset to base defaults, then copy selected config onto the shared runtime Config."""
        for name, value in _BASE_CONFIG_DEFAULTS.items():
            setattr(cls, name, value)
        for name in dir(source_cls):
            if not name.isupper():
                continue
            setattr(cls, name, getattr(source_cls, name))

    @classmethod
    def init_app(cls):
        """Initialize application configuration."""
        logger.info("Initializing application configuration...")

        # Log configuration values (masking sensitive data)
        logger.info("Configuration values:")
        logger.info(f"  - ENV_NAME: {cls.ENV_NAME}")
        logger.info(f"  - DEBUG: {cls.DEBUG}")
        logger.info(f"  - OPENAI_API_BASE: {cls.OPENAI_API_BASE}")
        logger.info(f"  - OPENAI_MODEL: {cls.OPENAI_MODEL}")
        logger.info(f"  - LLM_PROFILE: {cls.LLM_PROFILE}")
        logger.info(f"  - SMALL_LLM_MODE: {cls.SMALL_LLM_MODE}")
        logger.info(f"  - OPENAI_JSON_MODE: {cls.OPENAI_JSON_MODE}")
        logger.info(f"  - DEFAULT_LLM_MAX_TOKENS: {cls.DEFAULT_LLM_MAX_TOKENS}")
        logger.info(f"  - LLM_MAX_PARALLEL_REQUESTS: {cls.LLM_MAX_PARALLEL_REQUESTS}")
        logger.info(f"  - ANALYSIS_CHUNK_CHARS: {cls.ANALYSIS_CHUNK_CHARS}")
        logger.info(f"  - ENABLE_ANALYSIS_SYNTHESIS_LLM: {cls.ENABLE_ANALYSIS_SYNTHESIS_LLM}")
        logger.info(f"  - ENABLE_WBS_SKELETON_LLM: {cls.ENABLE_WBS_SKELETON_LLM}")
        logger.info(f"  - ENABLE_LLM_SEMANTIC_VALIDATION: {cls.ENABLE_LLM_SEMANTIC_VALIDATION}")
        logger.info(f"  - SMALL_LLM_ONLY_DEV_LLM_TASKS: {cls.SMALL_LLM_ONLY_DEV_LLM_TASKS}")
        logger.info(f"  - UPLOAD_FOLDER: {cls.UPLOAD_FOLDER}")
        logger.info(f"  - ARTIFACTS_ROOT: {cls.ARTIFACTS_ROOT}")
        logger.info(f"  - RESULTS_STORAGE_DIR: {cls.RESULTS_STORAGE_DIR}")
        logger.info(f"  - PROGRESS_STORAGE_DIR: {cls.PROGRESS_STORAGE_DIR}")
        logger.info(f"  - JOB_QUEUE_DB_PATH: {cls.JOB_QUEUE_DB_PATH}")
        logger.info(f"  - RATE_LIMIT_DB_PATH: {cls.RATE_LIMIT_DB_PATH}")
        logger.info(f"  - RESULT_TTL_SECONDS: {cls.RESULT_TTL_SECONDS}")
        logger.info(f"  - PROGRESS_TTL_SECONDS: {cls.PROGRESS_TTL_SECONDS}")
        logger.info(f"  - ARTIFACT_RETENTION_SECONDS: {cls.ARTIFACT_RETENTION_SECONDS}")
        logger.info(f"  - JOB_RETENTION_SECONDS: {cls.JOB_RETENTION_SECONDS}")
        logger.info(f"  - JOB_STALE_AFTER_SECONDS: {cls.JOB_STALE_AFTER_SECONDS}")
        logger.info(f"  - WORKER_POLL_INTERVAL_SECONDS: {cls.WORKER_POLL_INTERVAL_SECONDS}")
        logger.info(f"  - EMBEDDED_WORKER_ENABLED: {cls.EMBEDDED_WORKER_ENABLED}")
        logger.info(f"  - MAX_CONTENT_LENGTH: {cls.MAX_CONTENT_LENGTH} bytes")
        logger.info(f"  - WBS_TEMPLATE_PATH: {cls.WBS_TEMPLATE_PATH}")

        # Log stabilization configuration
        logger.info("Stabilization configuration:")
        logger.info(f"  - STABILIZATION_MODE: {StabilizationConfig.MODE}")
        logger.info(f"  - ENSEMBLE_ITERATIONS: {StabilizationConfig.ENSEMBLE_ITERATIONS}")
        logger.info(f"  - CONSENSUS_METHOD: {StabilizationConfig.CONSENSUS_METHOD}")
        logger.info(f"  - OUTLIER_THRESHOLD: {StabilizationConfig.OUTLIER_THRESHOLD}")
        logger.info(f"  - AUTO_NORMALIZE: {StabilizationConfig.AUTO_NORMALIZE}")
        logger.info(f"  - ESTIMATION_RULES_PATH: {StabilizationConfig.ESTIMATION_RULES_PATH}")
        
        # Check if API key is set
        if cls.OPENAI_API_KEY:
            masked_key = cls.OPENAI_API_KEY[:8] + "..." + cls.OPENAI_API_KEY[-4:] if len(cls.OPENAI_API_KEY) > 12 else "***"
            logger.info(f"  - OPENAI_API_KEY: {masked_key} (configured)")
        else:
            logger.warning("  - OPENAI_API_KEY: NOT SET! Application will not work without API key.")

        if cls.ENV_NAME == 'production':
            if cls.DEBUG:
                raise RuntimeError("DEBUG must be disabled in production.")
            if not cls.SECRET_KEY or cls.SECRET_KEY == 'dev-secret-key-change-in-production':
                raise RuntimeError("SECRET_KEY must be explicitly configured in production.")

        # Create upload folder if it doesn't exist
        if not os.path.exists(cls.UPLOAD_FOLDER):
            logger.info(f"Creating upload folder: {cls.UPLOAD_FOLDER}")
            os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
            logger.info("Upload folder created")
        else:
            logger.info(f"Upload folder exists: {cls.UPLOAD_FOLDER}")

        if not os.path.exists(cls.ARTIFACTS_ROOT):
            logger.info(f"Creating artifacts root: {cls.ARTIFACTS_ROOT}")
            os.makedirs(cls.ARTIFACTS_ROOT, exist_ok=True)
            logger.info("Artifacts root created")
        else:
            logger.info(f"Artifacts root exists: {cls.ARTIFACTS_ROOT}")

        if not os.path.exists(cls.RUNTIME_DIR):
            logger.info(f"Creating runtime dir: {cls.RUNTIME_DIR}")
            os.makedirs(cls.RUNTIME_DIR, exist_ok=True)
            logger.info("Runtime dir created")
        else:
            logger.info(f"Runtime dir exists: {cls.RUNTIME_DIR}")

        if not os.path.exists(cls.RESULTS_STORAGE_DIR):
            logger.info(f"Creating results storage dir: {cls.RESULTS_STORAGE_DIR}")
            os.makedirs(cls.RESULTS_STORAGE_DIR, exist_ok=True)
            logger.info("Results storage dir created")
        else:
            logger.info(f"Results storage dir exists: {cls.RESULTS_STORAGE_DIR}")

        if not os.path.exists(cls.PROGRESS_STORAGE_DIR):
            logger.info(f"Creating progress storage dir: {cls.PROGRESS_STORAGE_DIR}")
            os.makedirs(cls.PROGRESS_STORAGE_DIR, exist_ok=True)
            logger.info("Progress storage dir created")
        else:
            logger.info(f"Progress storage dir exists: {cls.PROGRESS_STORAGE_DIR}")

        # Create data folder if it doesn't exist
        data_folder = os.path.dirname(cls.ESTIMATION_RULES_PATH)
        if data_folder and not os.path.exists(data_folder):
            logger.info(f"Creating data folder: {data_folder}")
            os.makedirs(data_folder, exist_ok=True)
            logger.info("Data folder created")

        logger.info("Configuration initialization completed")

    @classmethod
    def allowed_file(cls, filename: str) -> bool:
        """Check if the file extension is allowed.
        
        Args:
            filename: Name of the file to check
            
        Returns:
            True if file extension is allowed, False otherwise
        """
        if '.' not in filename:
            return False
        extension = filename.rsplit('.', 1)[1].lower()
        is_allowed = extension in cls.ALLOWED_EXTENSIONS
        logger.debug(f"File extension check: {extension} -> {'allowed' if is_allowed else 'not allowed'}")
        return is_allowed

    @staticmethod
    def get_stabilization_config() -> dict:
        """Get stabilization configuration as dictionary.
        
        Returns:
            Dictionary with stabilization settings
        """
        return {
            'mode': StabilizationConfig.MODE,
            'ensemble_iterations': StabilizationConfig.ENSEMBLE_ITERATIONS,
            'consensus_method': StabilizationConfig.CONSENSUS_METHOD,
            'outlier_threshold': StabilizationConfig.OUTLIER_THRESHOLD,
            'auto_normalize': StabilizationConfig.AUTO_NORMALIZE,
            'apply_rules_validation': StabilizationConfig.APPLY_RULES_VALIDATION,
            'min_confidence_score': StabilizationConfig.MIN_CONFIDENCE_SCORE,
            'estimation_rules_path': StabilizationConfig.ESTIMATION_RULES_PATH
        }


class DevelopmentConfig(Config):
    """Development configuration."""
    ENV_NAME = 'development'
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    ENV_NAME = 'production'
    DEBUG = False
    # Use ensemble_validate for production by default
    STABILIZATION_MODE = os.getenv('STABILIZATION_MODE', 'ensemble_validate')
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing configuration."""
    ENV_NAME = 'testing'
    DEBUG = True
    TESTING = True
    SESSION_COOKIE_SECURE = False
    EMBEDDED_WORKER_ENABLED = False


_BASE_CONFIG_DEFAULTS = {
    name: getattr(Config, name)
    for name in dir(Config)
    if name.isupper()
}


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_active_config_class():
    """Resolve the active configuration class from environment variables."""
    config_name = os.getenv('APP_ENV', os.getenv('FLASK_ENV', 'development')).lower()
    return config.get(config_name, Config)
