"""
Configuration and persistence manager for OpenDictate.

Handles global settings, keyring credentials, SQLite database migrations,
application profiles, and dictation history storage.
"""

import os
import json
import sqlite3
import logging
import keyring
from typing import Dict, Any, Optional, Tuple, List

CONFIG_PATH = os.path.expanduser("~/.config/dictate-whisper/config.json")
DEFAULT_CONFIG: Dict[str, Any] = {
    "api_key": "",
    "llm_enabled": False,
    "model": "gemma-4"
}


class ConfigManager:
    """Manages application state, SQLite database persistence, and keyring storage."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        """Initialize base directory paths and ensure SQLite schema is created.

        Args:
            base_dir: Custom base directory path. Defaults to ~/.local/share/dictate-whisper.
        """
        self.base_dir = base_dir or os.path.expanduser("~/.local/share/dictate-whisper")
        self.db_path = os.path.join(self.base_dir, "dictate.db")
        self.init_database()

    def init_database(self) -> None:
        """Initialize the SQLite database schema for profiles, history, and settings."""
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS app_profiles (
                        app_class TEXT PRIMARY KEY,
                        system_prompt TEXT,
                        enable_vision BOOLEAN DEFAULT 0
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        app_class TEXT,
                        window_title TEXT,
                        original_text TEXT,
                        llm_text TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS global_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                ''')
                conn.commit()
            logging.info("SQLite database initialized successfully.")
        except Exception as e:
            logging.error(f"Error initializing SQLite database: {e}", exc_info=True)

    def load_config(self) -> Dict[str, Any]:
        """Load global configuration settings from SQLite database and Keyring.

        Performs legacy migration from config.json if present.

        Returns:
            Dict containing configuration key-value pairs.
        """
        cfg = DEFAULT_CONFIG.copy()

        # Legacy config.json migration
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    old_cfg = json.load(f)

                if "api_key" in old_cfg and old_cfg["api_key"]:
                    keyring.set_password("OpenDictate", "api_key", old_cfg["api_key"])
                    del old_cfg["api_key"]

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    for k, v in old_cfg.items():
                        cursor.execute(
                            "INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)",
                            (k, json.dumps(v))
                        )
                    conn.commit()

                os.remove(CONFIG_PATH)
                logging.info("Legacy config.json successfully migrated to SQLite database.")
            except Exception as e:
                logging.error(f"Error migrating legacy config.json: {e}", exc_info=True)

        # Load from SQLite database
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM global_settings")
                for row in cursor.fetchall():
                    cfg[row[0]] = json.loads(row[1])
        except Exception as e:
            logging.error(f"Error loading configuration from DB: {e}", exc_info=True)

        # Load API key securely from keyring
        try:
            stored_key = keyring.get_password("OpenDictate", "api_key")
            cfg["api_key"] = stored_key if stored_key else ""
        except Exception:
            cfg["api_key"] = ""

        return cfg

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration dictionary into SQLite database and Keyring.

        Args:
            config: Configuration dictionary to persist.
        """
        api_key = config.get("api_key", "")
        if api_key:
            keyring.set_password("OpenDictate", "api_key", api_key)
        else:
            try:
                keyring.delete_password("OpenDictate", "api_key")
            except Exception:
                pass

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for k, v in config.items():
                    if k != "api_key":
                        cursor.execute(
                            "INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)",
                            (k, json.dumps(v))
                        )
                conn.commit()
        except Exception as e:
            logging.error(f"Error saving configuration to DB: {e}", exc_info=True)

    def save_history_record(self, app_class: str, window_title: str, original_text: str, llm_text: Optional[str]) -> None:
        """Store dictation entry into SQLite history table.

        Args:
            app_class: Active application window class.
            window_title: Title of active window.
            original_text: Raw STT transcription text.
            llm_text: Post-processed AI text (if applicable).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO history (app_class, window_title, original_text, llm_text)
                    VALUES (?, ?, ?, ?)
                ''', (app_class or "unknown", window_title or "unknown", original_text, llm_text))
                conn.commit()
        except Exception as e:
            logging.error(f"Error saving dictation history to DB: {e}", exc_info=True)

    def get_app_profile(self, app_class: str) -> Tuple[Optional[str], bool]:
        """Fetch custom system prompt and vision flag for an application window class.

        Args:
            app_class: Target application window class.

        Returns:
            Tuple of (system_prompt, enable_vision).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT system_prompt, enable_vision FROM app_profiles WHERE app_class = ?",
                    (app_class,)
                )
                row = cursor.fetchone()
                if row:
                    return row[0], bool(row[1])
        except Exception as e:
            logging.error(f"Error fetching app profile for {app_class}: {e}")
        return None, False

    def get_recent_history(self, app_class: str, limit: int = 3) -> List[Tuple[Optional[str], Optional[str]]]:
        """Fetch recent dictation entries for contextual LLM prompts.

        Args:
            app_class: Target application window class.
            limit: Number of history items to retrieve.

        Returns:
            List of tuples (llm_text, original_text).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT llm_text, original_text FROM history WHERE app_class = ? ORDER BY id DESC LIMIT ?",
                    (app_class, limit)
                )
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error fetching recent history: {e}")
            return []
