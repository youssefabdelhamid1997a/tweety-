"""Local API-key configuration checks; all keys here are invented fixtures."""

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

from coach.config import ConfigError, KEY_FILENAME, load_api_key, remove_api_key, save_api_key, validate_api_key
import configure_api_key


KEY_A = "fictitious-unit-key-A"
KEY_B = "fictitious-unit-key-B"


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = Path(self.directory.name) / ".local"
        self.environment = patch.dict(os.environ, {"OPENDOTA_API_KEY": ""})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def write_json(self, value):
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / KEY_FILENAME).write_text(json.dumps(value), encoding="utf-8")

    def test_missing_config_is_optional_and_does_not_create_files(self):
        self.assertIsNone(load_api_key(self.cache))
        self.assertFalse(self.cache.exists())

    def test_validation_trims_edges_and_accepts_printable_ascii(self):
        self.assertEqual(validate_api_key("  " + KEY_A + "  "), KEY_A)
        self.assertEqual(validate_api_key("k" * 512), "k" * 512)

    def test_invalid_values_do_not_appear_in_errors(self):
        for value in (None, 123, [], {}, "", " ", "invalid secret with space", "invalid\nsecret", "invalid\tsecret", "invalid\x00secret", "not-ascii-é", "x" * 513):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ConfigError) as caught:
                validate_api_key(value)
            if isinstance(value, str) and value.strip():
                self.assertNotIn(value, str(caught.exception))

    def test_save_reload_replace_and_remove(self):
        save_api_key(self.cache, KEY_A)
        self.assertEqual(load_api_key(self.cache), KEY_A)
        save_api_key(self.cache, KEY_B)
        self.assertEqual(load_api_key(self.cache), KEY_B)
        self.assertTrue(remove_api_key(self.cache))
        self.assertFalse(remove_api_key(self.cache))
        self.assertIsNone(load_api_key(self.cache))

    @unittest.skipIf(os.name == "nt", "POSIX permission bits do not represent Windows ACLs")
    def test_local_key_file_has_private_posix_permissions(self):
        save_api_key(self.cache, KEY_A)
        self.assertEqual(stat.S_IMODE((self.cache / KEY_FILENAME).stat().st_mode), 0o600)

    def test_environment_precedes_file_without_overwriting_it(self):
        save_api_key(self.cache, KEY_A)
        before = (self.cache / KEY_FILENAME).read_bytes()
        with patch.dict(os.environ, {"OPENDOTA_API_KEY": KEY_B}):
            self.assertEqual(load_api_key(self.cache), KEY_B)
        self.assertEqual((self.cache / KEY_FILENAME).read_bytes(), before)
        self.assertEqual(load_api_key(self.cache), KEY_A)

    def test_blank_environment_uses_local_file(self):
        save_api_key(self.cache, KEY_A)
        with patch.dict(os.environ, {"OPENDOTA_API_KEY": "   "}):
            self.assertEqual(load_api_key(self.cache), KEY_A)

    def test_valid_environment_does_not_require_readable_local_json(self):
        self.cache.mkdir()
        (self.cache / KEY_FILENAME).write_text("not valid JSON", encoding="utf-8")
        with patch.dict(os.environ, {"OPENDOTA_API_KEY": KEY_A}):
            self.assertEqual(load_api_key(self.cache), KEY_A)

    def test_invalid_environment_is_not_silently_replaced_by_file(self):
        save_api_key(self.cache, KEY_A)
        invalid = "fictitious invalid secret"
        with patch.dict(os.environ, {"OPENDOTA_API_KEY": invalid}), self.assertRaises(ConfigError) as caught:
            load_api_key(self.cache)
        self.assertNotIn(invalid, str(caught.exception))

    def test_malformed_or_invalid_files_have_redacted_errors(self):
        invalid = "fictitious private value with spaces"
        for value in ({}, [], True, {"api_key": None}, {"api_key": invalid}):
            self.write_json(value)
            with self.subTest(shape=type(value).__name__), self.assertRaises(ConfigError) as caught:
                load_api_key(self.cache)
            self.assertNotIn(invalid, str(caught.exception))
        (self.cache / KEY_FILENAME).write_text("broken JSON " + KEY_A, encoding="utf-8")
        with self.assertRaises(ConfigError) as caught:
            load_api_key(self.cache)
        self.assertNotIn(KEY_A, str(caught.exception))

    def test_invalid_save_preserves_existing_key_and_other_files(self):
        save_api_key(self.cache, KEY_A)
        other = self.cache / "unrelated-settings.json"
        other.write_text('{"keep":true}', encoding="utf-8")
        before = (self.cache / KEY_FILENAME).read_bytes()
        with self.assertRaises(ConfigError):
            save_api_key(self.cache, "invalid secret value")
        self.assertEqual((self.cache / KEY_FILENAME).read_bytes(), before)
        self.assertEqual(other.read_text(encoding="utf-8"), '{"keep":true}')

    def test_failed_atomic_replace_preserves_key_and_cleans_temporary_file(self):
        save_api_key(self.cache, KEY_A)
        with patch("coach.config.os.replace", side_effect=OSError(KEY_B)), self.assertRaises(ConfigError) as caught:
            save_api_key(self.cache, KEY_B)
        self.assertEqual(load_api_key(self.cache), KEY_A)
        self.assertNotIn(KEY_B, str(caught.exception))
        self.assertEqual([p.name for p in self.cache.iterdir()], [KEY_FILENAME])

    def test_oversized_local_settings_are_rejected_without_echo(self):
        self.cache.mkdir()
        (self.cache / KEY_FILENAME).write_text(KEY_A * 600, encoding="utf-8")
        with self.assertRaises(ConfigError) as caught:
            load_api_key(self.cache)
        self.assertNotIn(KEY_A, str(caught.exception))


class ConfigureCLITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(configure_api_key, "ROOT", self.root)
        self.root_patch.start()
        self.environment = patch.dict(os.environ, {"OPENDOTA_API_KEY": ""})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.root_patch.stop()
        self.directory.cleanup()

    def test_noninteractive_secret_input_is_refused(self):
        output = io.StringIO()
        with patch("sys.argv", ["configure_api_key.py"]), patch("sys.stdin", io.StringIO(KEY_A + "\n")), patch("getpass.getpass") as prompt, contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = configure_api_key.main()
        self.assertNotEqual(status, 0)
        prompt.assert_not_called()
        self.assertFalse((self.root / ".local" / KEY_FILENAME).exists())
        self.assertNotIn(KEY_A, output.getvalue())

    def test_remove_is_noninteractive_and_never_prints_the_key(self):
        save_api_key(self.root / ".local", KEY_A)
        output = io.StringIO()
        with patch("sys.argv", ["configure_api_key.py", "--remove"]), patch("sys.stdin", io.StringIO()), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = configure_api_key.main()
        self.assertEqual(status, 0)
        self.assertFalse((self.root / ".local" / KEY_FILENAME).exists())
        self.assertNotIn(KEY_A, output.getvalue())

    def test_interactive_entry_saves_only_matching_hidden_values(self):
        output = io.StringIO()
        with patch("sys.argv", ["configure_api_key.py"]), patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", side_effect=[KEY_A, KEY_A]), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = configure_api_key.main()
        self.assertEqual(status, 0)
        self.assertEqual(load_api_key(self.root / ".local"), KEY_A)
        self.assertNotIn(KEY_A, output.getvalue())

    def test_mismatched_entry_keeps_previous_key(self):
        save_api_key(self.root / ".local", KEY_A)
        output = io.StringIO()
        with patch("sys.argv", ["configure_api_key.py"]), patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", side_effect=[KEY_B, KEY_B + "-different"]), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = configure_api_key.main()
        self.assertNotEqual(status, 0)
        self.assertEqual(load_api_key(self.root / ".local"), KEY_A)
        self.assertNotIn(KEY_B, output.getvalue())

    def test_getpass_echo_fallback_is_refused(self):
        def unsafe_prompt(*args, **kwargs):
            warnings.warn("Hidden input is unavailable", configure_api_key.getpass.GetPassWarning)
            return KEY_A
        output = io.StringIO()
        with patch("sys.argv", ["configure_api_key.py"]), patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", side_effect=unsafe_prompt), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = configure_api_key.main()
        self.assertNotEqual(status, 0)
        self.assertFalse((self.root / ".local" / KEY_FILENAME).exists())
        self.assertNotIn(KEY_A, output.getvalue())

    def test_accidental_secret_argument_is_not_echoed(self):
        output = io.StringIO()
        with patch("sys.argv", ["configure_api_key.py", "--api-key", KEY_A]), patch("getpass.getpass") as prompt, contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = configure_api_key.main()
        self.assertNotEqual(status, 0)
        prompt.assert_not_called()
        self.assertNotIn(KEY_A, output.getvalue())


if __name__ == "__main__":
    unittest.main()
