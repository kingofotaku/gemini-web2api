"""Install/remove the AutoConfig cookie-sync hook for gemini-web2api.

Copies firefox.cfg + defaults/pref/autoconfig.js into a Firefox install dir.

  py install.py [--firefox-dir <dir>] [--uninstall]

Default dir: G:\\FirefoxPortable\\App\\Firefox64 (the Firefox this machine uses).
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FIREFOX_DIR = r"G:\FirefoxPortable\App\Firefox64"
LAYOUT = {
    "firefox.cfg": "firefox.cfg",
    "autoconfig.js": os.path.join("defaults", "pref", "autoconfig.js"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firefox-dir", default=DEFAULT_FIREFOX_DIR,
                    help="Firefox application directory (contains firefox.exe)")
    ap.add_argument("--uninstall", action="store_true", help="remove the hook")
    args = ap.parse_args()

    ff_dir = os.path.abspath(args.firefox_dir)
    if not os.path.exists(ff_dir):
        print(f"error: no such directory: {ff_dir}", file=sys.stderr)
        return 1
    if not args.uninstall and not os.path.exists(os.path.join(ff_dir, "firefox.exe")):
        print(f"warning: {ff_dir} has no firefox.exe — is this the app directory?",
              file=sys.stderr)

    for src_name, rel in LAYOUT.items():
        dest = os.path.join(ff_dir, rel)
        if args.uninstall:
            if os.path.exists(dest):
                os.remove(dest)
                print("removed  ", dest)
            else:
                print("absent   ", dest)
            continue
        src = os.path.join(HERE, src_name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        print("installed", dest)
        if src_name == "firefox.cfg":
            with open(dest, encoding="utf-8") as f:
                if f.readline()[:2] != "//":
                    print("warning: firefox.cfg first line must be a comment", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
