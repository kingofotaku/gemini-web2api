"""Ticket routing: mismatch must be retryable, not fatal (TDD).

Upstream randomly ignores the model ticket (~15-30% of Pro requests observed
2026-09-25) and answers with the account default. The client must notice and
retry with a fresh ticket instead of silently returning the wrong model.
"""
import json
import unittest
from unittest import mock

from gemini_web2api.config import CONFIG
from gemini_web2api.gemini import (
    build_model_ticket,
    check_routing,
    upstream_echo,
)
from gemini_web2api import gemini as gw

FLASH_KEY = "fbb127bbb056c959"
PRO_KEY = "9d8ca3786ebdfbea"


def _wrb(label, fam, var, key=PRO_KEY):
    meta = [None] * 60
    meta[39] = key
    meta[42] = label
    meta[58] = fam
    meta[59] = var
    return json.dumps([["wrb.fr", None, json.dumps(meta)]]) + "\n" + "x" * 250


class CheckRoutingTests(unittest.TestCase):
    def test_matching_family_is_not_flagged(self):
        self.assertFalse(check_routing(_wrb("3.1 Pro", 3, 1), 3, 1))

    def test_mismatch_is_flagged_as_retryable(self):
        self.assertTrue(check_routing(_wrb("3.6 Flash", 1, 2), 3, 1))

    def test_unparseable_frame_is_not_flagged(self):
        self.assertFalse(check_routing("nothing here", 3, 1))


class StreamRetryTests(unittest.TestCase):
    """The stream path must retry the request when the first frame shows a
    different model, and must not retry once text has been emitted."""

    def _run_stream(self, frames_per_attempt):
        """Drive generate_stream with a fake httpx client.

        frames_per_attempt: list of frame-lists, one per attempt. Each frame is
        a raw line the fake response yields.
        """
        CONFIG["model_keys"] = {"flash": FLASH_KEY, "pro": PRO_KEY}
        CONFIG["retry_attempts"] = 3
        CONFIG["retry_delay_sec"] = 0
        attempts = {"n": 0}
        requests = []

        class FakeResp:
            def __init__(self, frames):
                self._frames = frames

            def raise_for_status(self):
                pass

            def iter_text(self):
                for f in self._frames:
                    yield f + "\n"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class FakeClient:
            def stream(self, method, url, content=None, headers=None):
                requests.append(headers)
                idx = attempts["n"]
                attempts["n"] += 1
                frames = frames_per_attempt[min(idx, len(frames_per_attempt) - 1)]
                return FakeResp(frames)

        with mock.patch.object(gw, "_get_httpx_client", return_value=FakeClient()):
            out = "".join(gw.generate_stream("hi", 3, 4, None, {80: 1}))

        return out, attempts["n"], requests

    def test_retries_once_when_first_frame_shows_wrong_model(self):
        fallback = _wrb("3.6 Flash", 1, 2).split("\n")[0]  # mismatch frame
        good = _wrb("3.1 Pro", 3, 1).split("\n")[0]        # correct frame
        text_frame = json.dumps([["wrb.fr", None, json.dumps(
            [None, ["c_1", "r_1"], None, None, [[None, ["PONG"]]]] + [None] * 60)]])
        out, n, requests = self._run_stream([[fallback], [text_frame]])

        self.assertEqual(n, 2, "expected a second attempt after the mismatch")
        self.assertIn("PONG", out)
        # Each attempt must carry its own ticket header.
        self.assertEqual(len({r["x-goog-ext-525001261-jspb"] for r in requests}), 2)

    def test_gives_up_after_all_attempts_when_always_mismatched(self):
        fallback = _wrb("3.6 Flash", 1, 2).split("\n")[0]
        with self.assertRaises(RuntimeError) as ctx:
            self._run_stream([[fallback], [fallback], [fallback]])
        self.assertIn("routing mismatch", str(ctx.exception))

    def test_does_not_retry_after_text_was_emitted(self):
        # Frame 1 is fine (echo says Pro), frame 2 emits text, frame 3 would be
        # garbage: after text is out, an error must end the stream, not retry.
        good = _wrb("3.1 Pro", 3, 1).split("\n")[0]
        text_frame = json.dumps([["wrb.fr", None, json.dumps(
            [None, ["c_1", "r_1"], None, None, [[None, ["PONG"]]]] + [None] * 60)]])
        out, n, _ = self._run_stream([[good, text_frame, "{broken"], []])
        self.assertEqual(n, 1, "must not retry after streaming text")
        self.assertIn("PONG", out)


class TicketShapeTests(unittest.TestCase):
    def test_browser_capture_contract_is_kept(self):
        CONFIG["model_keys"] = {"pro": PRO_KEY}
        try:
            t = json.loads(build_model_ticket(3, 1))
        finally:
            CONFIG.pop("model_keys", None)
        self.assertEqual(t[4], PRO_KEY)
        self.assertEqual((t[14], t[15]), (3, 1))
        self.assertEqual(t[11], 2)


if __name__ == "__main__":
    unittest.main()
