"""
LED service package for Minabox.

This package contains the configuration models and loading helpers for the
LED service. Hardware access, MQTT integration and API endpoints are added
in later iterations.
"""

from __future__ import annotations

from .config import load_app_config

__all__ = ["load_app_config"]
