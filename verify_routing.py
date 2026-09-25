#!/usr/bin/env python3
"""Live check: do the configured model_keys actually route?

Sends N requests per model through the real code path and reports which model
upstream answered with (from the response echo). Run it after refreshing
cookie.txt — an expired cookie or an exhausted quota shows up here as repeated
'mismatch' lines and a falling success rate, not as an error.

Exit code 1 if any model failed to route for every attempt.

Usage:
    python verify_routing.py [--count 6]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gemini_web2api.config import CONFIG, load_config  # noqa: E402
from gemini_web2api.gemini import (  # noqa: E402
    generate,
    upstream_echo,
)

# (model name, family, variant)
MODELS = [
    ("gemini-3.8-flash", 1, 1),
    ("gemini-3.1-pro", 3, 1),
]


def check(count: int) -> bool:
    load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    print("model_keys =", CONFIG.get("model_keys"), "\n")
    all_ok = True
    for name, family, variant in MODELS:
        ok = 0
        for i in range(count):
            try:
                raw = generate("reply exactly PONG", family, 4, None, {80: variant})
                echo = upstream_echo(raw)
                good = bool(echo and echo[1] == family and echo[2] == variant)
                ok += good
                print(f"  {name:18s} {i+1}/{count}: {echo} {'OK' if good else 'MISMATCH'}")
            except Exception as e:  # noqa: BLE001
                print(f"  {name:18s} {i+1}/{count}: FAIL {type(e).__name__}: {str(e)[:60]}")
        print(f"  => {name}: {ok}/{count} routed correctly\n")
        if ok == 0:
            all_ok = False
    return all_ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=6)
    args = ap.parse_args()
    sys.exit(0 if check(args.count) else 1)
