"""Ticket-based model routing tests (TDD).

Ticket 机制（源自 issue #82 + PR#100 AGENTS.md，本机实测验证 2026-09-25）：
- 文本路径的模型选择由 header `x-goog-ext-525001261-jspb`（ticket）决定，
  payload slot79 单独无效（无 ticket 时上游忽略它，回落账号默认）。
- ticket idx4 = model key（必须是账号页现存 ID）；idx14 = family；
  idx15 = variant。路由由 ticket 内嵌的 (family, variant) 决定 ——
  同一个 key 配 (1,1) 出 Flash、配 (3,1) 出 Pro。
- idx11 = 2（浏览器抓包恒定值），尾部 uuid 每次新生成。
- 契约：idx14 == payload slot79（= family），idx15 == payload slot80（= variant）。
"""
import json
import unittest

from gemini_web2api.config import CONFIG
from gemini_web2api.gemini import build_ticket, build_model_ticket, check_routing, upstream_echo
from gemini_web2api.models import MODELS, resolve_model

FLASH_KEY = "fbb127bbb056c959"


class TicketBuildTests(unittest.TestCase):
    def test_ticket_embeds_family_and_variant_at_14_15(self):
        t = json.loads(build_ticket("fbb127bbb056c959", 1, 1))

        self.assertEqual(t[4], "fbb127bbb056c959")   # model key
        self.assertEqual(t[11], 2)                   # browser-capture constant
        self.assertEqual(t[14], 1)                   # family
        self.assertEqual(t[15], 1)                   # variant
        self.assertEqual(t[8], [4, 5, 6, 8, 4, 5, 6, 8])
        self.assertEqual(len(t[16]), 36)             # fresh UUID, uppercase

    def test_ticket_uuid_is_fresh_per_call(self):
        a = json.loads(build_ticket("fbb127bbb056c959", 1, 1))[16]
        b = json.loads(build_ticket("fbb127bbb056c959", 1, 1))[16]

        self.assertNotEqual(a, b)


    def test_build_model_ticket_picks_key_by_family(self):
        CONFIG["model_keys"] = {"flash": FLASH_KEY, "pro": FLASH_KEY}
        try:
            flash = json.loads(build_model_ticket(1, 1))
            pro = json.loads(build_model_ticket(3, 1))

            self.assertEqual(flash[4], FLASH_KEY)
            self.assertEqual((flash[14], flash[15]), (1, 1))
            self.assertEqual((pro[14], pro[15]), (3, 1))
        finally:
            CONFIG.pop("model_keys", None)

    def test_build_model_ticket_is_none_without_configured_key(self):
        CONFIG.pop("model_keys", None)

        self.assertIsNone(build_model_ticket(1, 1))


class ModelTableTests(unittest.TestCase):
    def test_only_two_models_are_offered(self):
        self.assertEqual(set(MODELS.keys()), {"gemini-3.8-flash", "gemini-3.1-pro"})

    def test_flash_model_entries_match_ticket_contract(self):
        name, mode, think, err, extra = resolve_model("gemini-3.8-flash")

        self.assertIsNone(err)
        self.assertEqual(name, "gemini-3.8-flash")
        self.assertEqual(mode, 1)
        self.assertEqual(MODELS["gemini-3.8-flash"]["variant"], 1)
        self.assertEqual(extra[80], 1)

    def test_pro_model_entries_match_ticket_contract(self):
        name, mode, think, err, extra = resolve_model("gemini-3.1-pro")

        self.assertIsNone(err)
        self.assertEqual(mode, 3)
        self.assertEqual(MODELS["gemini-3.1-pro"]["variant"], 1)
        self.assertEqual(extra[80], 1)

    def test_think_override_still_works(self):
        _, _, think, err, _ = resolve_model("gemini-3.1-pro@think=2")

        self.assertIsNone(err)
        self.assertEqual(think, 2)


class EchoTests(unittest.TestCase):
    @staticmethod
    def _wrb(label, fam, var, key="fbb127bbb056c959"):
        meta = [None] * 60
        meta[39] = key
        meta[42] = label
        meta[58] = fam
        meta[59] = var
        return json.dumps([["wrb.fr", None, json.dumps(meta)]]) + "\n" + "x" * 250

    def test_upstream_echo_reads_label_family_variant(self):
        self.assertEqual(upstream_echo(self._wrb("3.1 Pro", 3, 1)), ("3.1 Pro", 3, 1))

    def test_upstream_echo_returns_none_without_wrb(self):
        self.assertIsNone(upstream_echo("nothing here"))

    def test_check_routing_accepts_matching_family(self):
        self.assertIsNone(check_routing(self._wrb("3.1 Pro", 3, 1), 3, 1))

    def test_check_routing_flags_silent_fallback(self):
        # 无 ticket 时上游回落账号默认（family 6）——必须能被检测到
        self.assertIn("mismatch", check_routing(self._wrb("3.5 Flash-Lite", 6, 1), 3, 1).lower())


if __name__ == "__main__":
    unittest.main()
