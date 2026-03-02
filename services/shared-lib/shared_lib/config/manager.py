"""Generic JSON config manager with hot-reload and optional callbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, TypeVar

import structlog
from pydantic import BaseModel

from ..exceptions import ConfigError
from .loader import load_json_config

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class JsonConfigManager:
    """Manages a single JSON config file with load, save, reload and optional callbacks.

    Use with a Pydantic schema class. Services can pass their schema and path;
    optional reload callbacks are notified on update_config and reload_config.
    """

    def __init__(
        self,
        config_path: Path,
        schema_class: type[T],
        *,
        create_if_missing: bool = False,
        default_factory: Callable[[], T] | None = None,
    ) -> None:
        self._config_path = config_path
        self._schema_class = schema_class
        self._create_if_missing = create_if_missing
        self._default_factory = default_factory
        self._current_config: T | None = None
        self._reload_callbacks: list[Callable[[T], None]] = []

    def load_config(self) -> T:
        """Load config from disk and cache it."""
        config = load_json_config(
            self._config_path,
            self._schema_class,
            create_if_missing=self._create_if_missing,
            default_factory=self._default_factory,
        )
        self._current_config = config
        logger.debug("config_loaded", path=str(self._config_path))
        return config

    def get_current_config(self) -> T | None:
        """Return the last loaded config, or None if not yet loaded."""
        return self._current_config

    def update_config(self, new_config: T) -> None:
        """Validate (already done by caller), write to disk, update cache, notify callbacks."""
        try:
            config_dict = new_config.model_dump(mode="json")
            config_json = json.dumps(config_dict, indent=2, ensure_ascii=False)
        except Exception as exc:
            raise ConfigError(f"Failed to serialize configuration: {exc}") from exc

        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(config_json, encoding="utf-8")
        except OSError as exc:
            raise ConfigError(
                f"Failed to write configuration to {self._config_path}: {exc}"
            ) from exc

        self._current_config = new_config
        logger.debug("config_updated", path=str(self._config_path))
        self._notify_callbacks(new_config)

    def reload_config(self) -> T:
        """Reload from disk and notify callbacks."""
        config = self.load_config()
        self._notify_callbacks(config)
        return config

    def register_reload_callback(self, callback: Callable[[T], None]) -> None:
        """Register a callback to be invoked when config is reloaded or updated."""
        self._reload_callbacks.append(callback)
        logger.debug("reload_callback_registered", callback=callback.__name__)

    def _notify_callbacks(self, config: T) -> None:
        for callback in self._reload_callbacks:
            try:
                callback(config)
            except Exception as exc:
                logger.error(
                    "reload_callback_failed",
                    callback=callback.__name__,
                    error=str(exc),
                    exc_info=True,
                )
