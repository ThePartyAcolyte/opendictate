"""
Configuration and persistence manager for OpenDictate.

Handles global settings, keyring credentials, SQLite database migrations,
application profiles, and dictation history storage.
"""

import os
import json
import sqlite3
import logging
from typing import Dict, Any, Optional, Tuple, List

try:
    import keyring
except ImportError:
    keyring = None

CONFIG_PATH = os.path.expanduser("~/.config/opendictate/config.json")
DEFAULT_CONFIG: Dict[str, Any] = {
    "api_key": "",
    "ai_enabled": False,
    "model": "gemma-4-26b-a4b-it",
    "restore_window_focus": False,
    "realtime_mode": True,
    "chunk_silence_duration": 0.85,
    "chunk_max_duration": 30.0,
    "chunk_fallback_silence_duration": 0.5,
    "chunk_min_duration": 3.0,
    "chunk_speech_pad": 0.3,
    "chunk_vad_energy_threshold": 0.030,
    "bubble_mode": "auto",
    "bubble_text_collapsed": False,
    "hide_bubble": False,
    "indicator_mode": "auto",
    "use_appindicator": True,
    "use_gnome_ext": True,
    "check_updates": False,
    "update_frequency": "monthly",
    "update_channel": "stable",
    "last_update_check": 0,
    "available_update_version": "",
    "available_update_url": "",
    "available_update_notes": "",
    "update_dismissed_version": "",
    "initial_setup_completed": False,
    "whisper_device": "auto",
    "whisper_compute_type": "default",
    "whisper_cpu_threads": 0,
    "repetition_penalty": 1.1,
    "no_repeat_ngram_size": 0,
    "hallucination_silence_threshold": 2.0,
    "condition_on_previous_text": True,
    "beam_patience": 1.0,
    "length_penalty": 1.0,
    "vad_filter": False,
    "vad_threshold": 0.5,
    "vad_min_speech_duration_ms": 250,
    "vad_min_silence_duration_ms": 2000,
    "vad_speech_pad_ms": 400,
    "stt_backend": "local_whisper",
    "gemini_live_mode": "SMART",
    "gemini_live_model": "gemini-3.5-transcribe-live",
    "llm_thinking_level": "minimal",
    "voice_commands_enabled": False,
    "voice_command_threshold": 0.70,
    "voice_command_silence_pause": 1.5,
    "voice_vad_threshold": 0.075,
    "voice_vad_noise_floor": 0.030,
    "echo_cancellation_enabled": True
}


def is_api_available(config: Dict[str, Any]) -> bool:
    """Check if a valid Gemini API key is configured.

    Args:
        config: Application configuration dictionary.

    Returns:
        True if api_key is non-empty, False otherwise.
    """
    key = config.get("api_key", "")
    return bool(key and str(key).strip())


class ConfigManager:
    """Manages application state, SQLite database persistence, and keyring storage."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        """Initialize base directory paths and ensure SQLite schema is created.

        Args:
            base_dir: Custom base directory path. Defaults to ~/.local/share/opendictate.
        """
        self.base_dir = base_dir or os.path.expanduser("~/.local/share/opendictate")
        self.db_path = os.path.join(self.base_dir, "opendictate.db")
        self._cached_api_key: Optional[str] = None
        self.init_database()

    def _get_api_key_safe(self) -> str:
        """Retrieve API key from system keyring with retries and in-memory cache protection.

        Returns:
            Decrypted API key string, or empty string if not configured.
        """
        if not keyring:
            return self._cached_api_key or ""

        for attempt in range(3):
            try:
                stored_key = keyring.get_password("OpenDictate", "api_key")
                if stored_key and stored_key.strip():
                    self._cached_api_key = stored_key.strip()
                    return self._cached_api_key
                if self._cached_api_key:
                    return self._cached_api_key
                return ""
            except Exception as e:
                logging.debug(f"Keyring retrieval attempt {attempt + 1} failed: {e}")
                time.sleep(0.05)

        return self._cached_api_key or ""

    def init_database(self) -> None:
        """Initialize the SQLite database schema and handle version migrations."""
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA user_version")
                current_version = cursor.fetchone()[0]

                if current_version == 0:
                    logging.info("Initializing new database schema (v1).")
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
                    cursor.execute("PRAGMA user_version = 2")
                elif current_version > 0:
                    self._run_migrations(cursor, current_version)

                conn.commit()
            logging.info(f"SQLite database ready (version {current_version if current_version > 0 else 2}).")
        except Exception as e:
            logging.error(f"Error initializing SQLite database: {e}", exc_info=True)

    def _run_migrations(self, cursor: sqlite3.Cursor, current_version: int) -> None:
        """Execute incremental structural migrations based on current schema version."""
        target_version = 2
        if current_version >= target_version:
            return

        logging.info(f"Migrating database from version {current_version} to {target_version}...")
        
        if current_version < 2:
            logging.info("Applying migration v1 -> v2 (pruning deprecated chunk settings)...")
            cursor.execute("DELETE FROM global_settings WHERE key IN ('chunk_stride', 'chunk_overlap', 'chunk_tolerance')")
            cursor.execute("PRAGMA user_version = 2")
        
        logging.info("Database migration completed successfully.")

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
                    if keyring:
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

        # Load API key securely from keyring with retry and cache protection
        cfg["api_key"] = self._get_api_key_safe()

        return cfg

    def save_config(self, config: Dict[str, Any], explicit_api_key_update: bool = False) -> None:
        """Save configuration dictionary into SQLite database and Keyring safely.

        Args:
            config: Configuration dictionary to persist.
            explicit_api_key_update: True if called from UI where API key was explicitly edited/cleared.
        """
        api_key = config.get("api_key")
        if keyring:
            if api_key and str(api_key).strip():
                clean_key = str(api_key).strip()
                if clean_key != self._cached_api_key:
                    try:
                        keyring.set_password("OpenDictate", "api_key", clean_key)
                        self._cached_api_key = clean_key
                    except Exception as e:
                        logging.error(f"Error saving API key to keyring: {e}", exc_info=True)
            elif explicit_api_key_update and api_key == "":
                try:
                    keyring.delete_password("OpenDictate", "api_key")
                    self._cached_api_key = ""
                except Exception as e:
                    logging.debug(f"Error deleting API key from keyring: {e}")

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
