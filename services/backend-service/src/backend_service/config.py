"""Global configuration instance for Backend Service."""

from pathlib import Path

from backend_service.config_manager import ConfigManager
from backend_service.config_schema import BackendConfig

# Global config manager instance
config_manager = ConfigManager(config_path=Path("config/backend.json"))

# Load configuration on module import
try:
    config = config_manager.load()
except Exception as e:
    # Log error but don't crash on import
    import structlog

    logger = structlog.get_logger(__name__)
    logger.error("config_load_failed_on_import", error=str(e))
    raise


def get_config() -> BackendConfig:
    """Get current configuration instance.

    Returns:
        Current BackendConfig instance
    """
    return config_manager.config


def reload_config() -> BackendConfig:
    """Reload configuration from disk.

    Returns:
        Reloaded BackendConfig instance
    """
    return config_manager.reload()
