"""Optional local OpenDota credentials, never included in HTTP responses or exports.

The settings file is plain text, not an encrypted credential vault. Its directory
belongs to the app's ignored .local folder. New POSIX files use private permissions;
Windows files inherit the containing user's folder permissions.
"""

import json
import os
import tempfile
from pathlib import Path

KEY_FILENAME = "opendota-api-key.json"
ENVIRONMENT_NAME = "OPENDOTA_API_KEY"


class ConfigError(ValueError):
    """An actionable settings error that never includes credential values."""


def validate_api_key(value):
    if not isinstance(value, str):
        raise ConfigError("The OpenDota API key must be text. Paste only the key, without an Authorization or Bearer prefix.")
    key = value.strip()
    if not key or len(key) > 512 or any(not 33 <= ord(char) <= 126 for char in key):
        raise ConfigError("The OpenDota API key must contain 1–512 printable ASCII characters without spaces or control characters. Paste only the key.")
    return key


def load_api_key(cache_dir):
    """Use a nonempty process variable first, then the optional local key file."""
    environment_key = os.environ.get(ENVIRONMENT_NAME, "")
    if environment_key.strip():
        try:
            return validate_api_key(environment_key)
        except ConfigError:
            raise ConfigError("OPENDOTA_API_KEY is set but invalid. Correct or remove that environment variable before starting the coach.") from None
    path = Path(cache_dir) / KEY_FILENAME
    try:
        with path.open("rb") as handle:
            body = handle.read(8193)
    except FileNotFoundError:
        return None
    except OSError:
        raise ConfigError("Could not read the local OpenDota API key settings. Check folder access or run set-api-key.bat again.") from None
    try:
        if len(body) > 8192:
            raise ValueError()
        settings = json.loads(body.decode("utf-8"))
        if not isinstance(settings, dict):
            raise ValueError()
        return validate_api_key(settings.get("api_key"))
    except (ValueError, UnicodeError):
        raise ConfigError("The local OpenDota API key settings are unreadable or invalid. Run set-api-key.bat to replace them, or configure_api_key.py --remove to remove the local key.") from None


def save_api_key(cache_dir, key):
    """Atomically replace only the local key file after validating the new key."""
    key = validate_api_key(key)
    directory = Path(cache_dir)
    temporary_path = None
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="opendota-key-", suffix=".tmp", dir=directory)
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"api_key": key}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, directory / KEY_FILENAME)
    except OSError:
        raise ConfigError("Could not save the local OpenDota API key. Check that the app folder is writable. Existing settings were not intentionally removed.") from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def remove_api_key(cache_dir):
    """Remove the local file only; leave process environment bindings unchanged."""
    try:
        (Path(cache_dir) / KEY_FILENAME).unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise ConfigError("Could not remove the local OpenDota API key settings. Check folder access and try again.") from None
