"""Account selection: the exported auth json must drive /u/N on the wire.

Regression guard for the bug where the package's load_cookie() read the cookie
string but ignored auth_user, so every request went to /app (account 0) and the
upstream answered with that account's default model — 3.1 Pro fell back to a
Flash model and 3.8 Flash to Flash-Lite, with no error surfaced.
"""
import json
import os
import tempfile
import unittest

from gemini_web2api import gemini
from gemini_web2api.config import CONFIG


class AuthFileAccountTests(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(CONFIG)
        self.original_loaded = gemini._auth_fields_loaded
        gemini._auth_fields_loaded = False
        gemini._cookie_cache.update({"str": "", "sapisid": None, "mtime": 0, "size": -1})
        CONFIG["auth_user"] = None
        handle, self.cookie_file = tempfile.mkstemp(suffix=".json")
        with os.fdopen(handle, "w") as f:
            json.dump({
                "cookie": "SID=abc; SAPISID=def",
                "sapisid": "def",
                "auth_user": "1",
                "xsrf_token": "TOKEN_FROM_FILE",
            }, f)
        CONFIG["cookie_file"] = self.cookie_file

    def tearDown(self):
        os.unlink(self.cookie_file)
        gemini._auth_fields_loaded = self.original_loaded
        gemini._cookie_cache.update({"str": "", "sapisid": None, "mtime": 0, "size": -1})
        CONFIG.clear()
        CONFIG.update(self.original_config)

    def test_auth_json_supplies_account_and_page_tokens(self):
        gemini.load_cookie()

        self.assertEqual(CONFIG["auth_user"], "1")
        self.assertEqual(CONFIG["xsrf_token"], "TOKEN_FROM_FILE")
        self.assertEqual(gemini._account_prefix(), "/u/1")

    def test_requests_target_the_account_from_the_auth_json(self):
        url = gemini._get_url("session-id")
        headers = gemini._build_headers(family=1, variant=1)

        self.assertIn("gemini.google.com/u/1/_/BardChatUi/", url)
        self.assertEqual(headers["X-Goog-AuthUser"], "1")
        self.assertEqual(headers["Referer"], "https://gemini.google.com/u/1/app")


if __name__ == "__main__":
    unittest.main()
