#!/usr/bin/env python3
"""
Panic Button Configuration Loader
Loads and validates configuration from panic.yaml
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, List

class PanicConfig:
    """Configuration manager for panic button system."""

    def __init__(self, config_path: str = "config/panic.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {self.config_path}")

            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load config: {e}")

    def _validate_config(self):
        """Validate required configuration fields."""
        required_fields = [
            'alert', 'lock', 'verify', 'http', 'backoff'
        ]

        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required config field: {field}")

        # Validate Telegram settings if using telegram alerts
        if self.config['alert']['channel'] == 'telegram':
            telegram_config = self.config['alert'].get('telegram', {})
            if not telegram_config.get('bot_token') or not telegram_config.get('chat_id'):
                print("[CONFIG] WARNING: Telegram bot_token or chat_id not configured. Alerts will be disabled.")

    @property
    def telegram_bot_token(self) -> str:
        """Get Telegram bot token."""
        return self.config['alert']['telegram']['bot_token']

    @property
    def telegram_chat_id(self) -> str:
        """Get Telegram chat ID."""
        return self.config['alert']['telegram']['chat_id']

    @property
    def lock_file_path(self) -> str:
        """Get lock file path."""
        return self.config['lock']['file_path']

    @property
    def verify_timeout(self) -> int:
        """Get verification timeout in seconds."""
        return self.config['verify']['timeout_sec']

    @property
    def verify_poll_ms(self) -> int:
        """Get verification polling interval in milliseconds."""
        return self.config['verify']['poll_ms']

    @property
    def max_retries(self) -> int:
        """Get maximum retry attempts."""
        return self.config['verify']['max_retries']

    @property
    def http_port(self) -> int:
        """Get HTTP server port."""
        return self.config['http']['port']

    @property
    def http_host(self) -> str:
        """Get HTTP server host."""
        return self.config['http']['host']

    @property
    def http_allowlist(self) -> List[str]:
        """Get HTTP server IP allowlist."""
        return self.config['http']['allowlist']

    @property
    def initial_backoff_ms(self) -> int:
        """Get initial backoff delay in milliseconds."""
        return self.config['backoff']['initial_ms']

    @property
    def max_backoff_ms(self) -> int:
        """Get maximum backoff delay in milliseconds."""
        return self.config['backoff']['max_ms']

    @property
    def backoff_multiplier(self) -> float:
        """Get backoff multiplier."""
        return self.config['backoff']['multiplier']

    @property
    def symbols_scope(self) -> str:
        """Get symbols scope setting."""
        return self.config.get('symbols', {}).get('scope', 'open_positions_only')

# Global config instance
config = None

def load_config(config_path: str = "config/panic.yaml") -> PanicConfig:
    """Load and return global config instance."""
    global config
    if config is None:
        config = PanicConfig(config_path)
    return config

def get_config() -> PanicConfig:
    """Get existing config instance or load default."""
    global config
    if config is None:
        config = load_config()
    return config