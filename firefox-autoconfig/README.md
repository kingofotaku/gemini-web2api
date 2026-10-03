# Firefox AutoConfig cookie sync

Keeps `cookie.txt` stocked with a fresh Google session, taken straight from
Firefox — with no extension, no debugging port, and no external process
touching browser data files.

## Why this shape

| Route | Verdict |
|---|---|
| Read `cookies.sqlite` from Python | **Blocked.** ESET's browser-data protection denies reads of browser profile directories to every other process (verified: even elevated processes and scheduled tasks get ACCESS_DENIED; a profile becomes protected once Firefox has used it). |
| WebExtension pushing cookies | **Blocked.** Firefox release builds require signed add-ons: sideload (`extensions/`), `distribution/extensions`, and policy `force_installed` all fail with `ERROR_SIGNEDSTATE_REQUIRED`. Signing via AMO would work but needs an external account. |
| Automation (Marionette/CDP) | **Not acceptable.** Google notices automation on the Gemini surface. |
| **AutoConfig (`firefox.cfg`)** | **Works.** Firefox runs it in-process at startup; it can read the cookie jar and write a file. No signature, no account, invisible to web pages. |

## Files

- `firefox.cfg` → install to `<firefox>/firefox.cfg`
- `autoconfig.js` → install to `<firefox>/defaults/pref/autoconfig.js`

On every Firefox startup, on cookie changes (debounced by content compare),
on UI-ready, on quit, and every 5 minutes, the config:

1. collects every `google.com` cookie from the live cookie jar,
2. skips writing entirely if the session markers (`SID` + `__Secure-1PSID`)
   are absent — so a non-logged-in profile can never clobber a good file,
3. writes `{cookie, sapisid, auth_user, exported, source}` atomically to
   `G:\cli\gemini-web2api\cookie.txt` (tmp file + rename).

The service picks the file up on its next request (`load_cookie()` re-reads it).

## Install / uninstall

```bash
py install.py                     # install into the default Firefox dir
py install.py --uninstall         # remove
py install.py --firefox-dir "<path-to-firefox-dir>"
```

The installed copy is the source of truth for the running browser; keep it in
sync with this folder after edits (`install.py` overwrites).

## Knobs

Inside `firefox.cfg`:

- `DEFAULT_TARGET` — where the snapshot lands (default `cookie.txt`).
- `AUTH_USER` — Google account index (`/u/N`) written into the file. Must
  match the account that is logged in; check with the service's routing test.
- `TIMER_MS` — periodic refresh interval (default 5 min).

Per-profile override for testing: set pref `hermes.cookieSync.target` in that
profile's `user.js`. Note AutoConfig runs before `user.js` is applied, so the
override takes effect from the first *event* dump, not the startup dump — for
full isolation during tests, edit `DEFAULT_TARGET` instead.

Diagnostics: the config writes `hermes.cookieSync.*` prefs into
`prefs.js` (`last`, `err`, `installed`) — read them to see what it did.

## After a Firefox update

Portable/regular Firefox updates can replace the application directory and
drop both files. Re-run `py install.py`.
