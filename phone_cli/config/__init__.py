"""Configuration module for phone-cli."""

from phone_cli.config.apps import APP_PACKAGES
from phone_cli.config.apps_harmonyos import APP_PACKAGES as APP_PACKAGES_HARMONYOS
from phone_cli.config.apps_ios import APP_PACKAGES as APP_PACKAGES_IOS
from phone_cli.config.i18n import get_message, get_messages
from phone_cli.config.timing import (
    TIMING_CONFIG,
    ActionTimingConfig,
    ConnectionTimingConfig,
    DeviceTimingConfig,
    TimingConfig,
    get_timing_config,
    update_timing_config,
)

__all__ = [
    "APP_PACKAGES",
    "APP_PACKAGES_HARMONYOS",
    "APP_PACKAGES_IOS",
    "get_messages",
    "get_message",
    "TIMING_CONFIG",
    "TimingConfig",
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "get_timing_config",
    "update_timing_config",
]
