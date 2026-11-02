"""Masked local API-key setup; no credentials are accepted on the command line."""

import argparse
import getpass
import os
import sys
import warnings
from pathlib import Path

from coach.config import ConfigError, ENVIRONMENT_NAME, KEY_FILENAME, remove_api_key, save_api_key, validate_api_key

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Configure an optional OpenDota API key on this computer.")
    parser.add_argument("--remove", action="store_true", help="Remove only the locally saved key; leave environment variables unchanged")
    arguments = sys.argv[1:]
    if arguments not in ([], ["--remove"], ["--help"], ["-h"]):
        print("Only --remove is supported. Do not put an API key on the command line; use the hidden interactive prompt instead.")
        return 2
    args = parser.parse_args(arguments)
    cache_dir = ROOT / ".local"
    environment_present = bool(os.environ.get(ENVIRONMENT_NAME, "").strip())
    if environment_present:
        print("OPENDOTA_API_KEY is set in this process and takes precedence over the local settings file. Its value is not displayed.")
    try:
        if args.remove:
            removed = remove_api_key(cache_dir)
            print("Local OpenDota API key removed." if removed else "No local OpenDota API key was saved.")
            if environment_present:
                print("The environment variable was not removed. Clear it separately to use the public API without a key.")
            print("Close every running coach console, then double-click run.bat to apply the change.")
            return 0
        if not sys.stdin.isatty():
            print("API-key entry requires an interactive terminal so the key stays hidden. Open set-api-key.bat or run this command directly in PowerShell. Do not pipe the key into it.")
            return 1
        print("Paste your OpenDota API key below. Input is hidden; press Enter after pasting.")
        print(f"It will be saved locally in .local/{KEY_FILENAME}. This file is plain text, not encrypted; do not share the .local folder.")
        with warnings.catch_warnings():
            # getpass otherwise falls back to echoed input when terminal control
            # fails. Never accept that fallback for a credential prompt.
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = validate_api_key(getpass.getpass("OpenDota API key: "))
            confirmation = validate_api_key(getpass.getpass("Paste the same key again: "))
        if key != confirmation:
            print("The entries did not match. Nothing was saved. Run set-api-key.bat again.")
            return 1
        save_api_key(cache_dir, key)
        print("OpenDota API key saved. Its value is not displayed.")
        if environment_present:
            print("The process environment variable still takes precedence over this saved key.")
        print("Close every running coach console, then double-click run.bat. The restarted coach will use the configured key.")
        return 0
    except ConfigError as error:
        print(str(error))
        return 1
    except (getpass.GetPassWarning, EOFError):
        print("Hidden input is unavailable in this terminal. Nothing was saved. Open set-api-key.bat in a normal Windows console and try again.")
        return 1
    except KeyboardInterrupt:
        print("\nSetup cancelled. Nothing was saved.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
