"""Ground truth captured from Google's own browser session (2026-09-25).

Runs while the page is open: clicks the model the user picks in the UI, sends a
message, and prints the ticket Google itself used plus the echo label it got
back. Use it whenever the ticket layout or model list is in doubt — the earlier
conclusion ('3.8 is just an alias for 3.6') came from testing our own ticket
template instead of reading Google's, and was wrong.
"""
import json
import sys
import time
import urllib.request

DAEMON = "http://127.0.0.1:9333/cdp"
OPT_SEL = "[role=option],mat-option,[role=menuitem],.mat-mdc-option"


def cdp(method, params=None, sid=None, timeout=30000):
    body = {"method": method, "params": params or {}, "timeout": timeout}
    if sid:
        body["sessionId"] = sid
    req = urllib.request.Request(DAEMON, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(opener.open(req, timeout=timeout).read().decode())


def ev(expr, sid, timeout=25000):
    r = cdp("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                 "awaitPromise": True}, sid, timeout)
    res = r.get("result", {}).get("result", {})
    return res.get("value") if res.get("subtype") != "error" else "JS_ERROR: " + str(res.get("description"))[:200]


def attach():
    targets = cdp("Target.getTargets")["result"]["targetInfos"]
    gem = [t for t in targets if t.get("type") == "page" and "gemini.google.com" in t.get("url", "")]
    if not gem:
        raise SystemExit("no gemini tab open")
    sid = cdp("Target.attachToTarget", {"targetId": gem[0]["targetId"], "flatten": True})["result"]["sessionId"]
    cdp("Runtime.enable", {}, sid)
    return sid


def hook(sid):
    ev("""
    (() => {
      window.__cap = [];
      const of = window.fetch;
      window.fetch = async function(input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        try {
          if (/StreamGenerate/.test(url)) {
            const h = (init && init.headers) || {};
            const obj = {};
            for (const [k, v] of (h instanceof Headers ? h.entries() : Object.entries(h))) obj[k.toLowerCase()] = v;
            const rec = {ticket: obj['x-goog-ext-525001261-jspb'] || null, resp: null};
            window.__cap.push(rec);
            const r = await of.apply(this, arguments);
            try { r.clone().text().then(t => { rec.resp = t.slice(0, 60000); }); } catch (e) {}
            return r;
          }
        } catch (e) {}
        return of.apply(this, arguments);
      };
      const oo = XMLHttpRequest.prototype.open, os_ = XMLHttpRequest.prototype.send,
            oh = XMLHttpRequest.prototype.setRequestHeader;
      XMLHttpRequest.prototype.open = function(m, u) { this.__u = u; return oo.apply(this, arguments); };
      XMLHttpRequest.prototype.setRequestHeader = function(k, v) {
        if (/525001261/.test(k)) this.__t = v;
        return oh.apply(this, arguments);
      };
      XMLHttpRequest.prototype.send = function(b) {
        if (this.__u && /StreamGenerate/.test(String(this.__u))) {
          const rec = {ticket: this.__t || null, resp: null};
          window.__cap.push(rec);
          this.addEventListener('loadend', () => { try { rec.resp = (this.responseText || '').slice(0, 60000); } catch (e) {} });
        }
        return os_.apply(this, arguments);
      };
      return 'ok';
    })()
    """, sid)


def pick(sid, want):
    """Open the picker and click the option matching `want` (e.g. '3.8')."""
    ev("""(() => { const b = [...document.querySelectorAll('button,[role=button]')]
          .find(x => /^(Fast|Thinking|Pro|Flash)$/i.test((x.textContent||'').trim()));
          if (b) b.click(); return 'opened'; })()""", sid)
    time.sleep(2)
    return ev(f"""
    (() => {{
      const o = [...document.querySelectorAll('{OPT_SEL}')].find(e => e.textContent && e.textContent.indexOf('{want}') >= 0);
      if (!o) return 'option not found: ' + [...document.querySelectorAll('{OPT_SEL}')].map(e=>(e.textContent||'').trim().slice(0,20)).join(' | ');
      o.click(); return 'clicked: ' + (o.textContent||'').replace(/\\s+/g,' ').trim().slice(0,40);
    }})()
    """, sid)


def send(sid, text):
    return ev("""
    (async () => {
      const ta = document.querySelector('textarea, rich-textarea .ql-editor, [contenteditable=true]');
      if (!ta) return 'no input';
      ta.focus();
      if ('value' in ta) { ta.value = %s; ta.dispatchEvent(new Event('input', {bubbles:true})); }
      else { ta.textContent = %s; ta.dispatchEvent(new InputEvent('input', {bubbles:true})); }
      await new Promise(r => setTimeout(r, 500));
      const b = [...document.querySelectorAll('button')].find(x => /send|发送/i.test(x.getAttribute('aria-label')||''));
      if (b && !b.disabled) { b.click(); return 'sent'; }
      ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, bubbles:true}));
      return 'enter';
    })()
    """ % (json.dumps(text), json.dumps(text)), sid)


def report(sid):
    cap = json.loads(ev("JSON.stringify((window.__cap||[]).map(r => ({ticket:r.ticket, resp:(r.resp||'').slice(0,40000)})))", sid) or "[]")
    for i, c in enumerate(cap):
        print(f"--- capture {i} ---")
        if c.get("ticket"):
            a = json.loads(c["ticket"])
            print("ticket key(idx4) =", repr(a[4]), "| idx8 =", a[8], "| idx11 =", repr(a[11]), "| idx14/15 =", a[14], a[15])
        for line in (c.get("resp") or "").split("\n"):
            if '"wrb.fr"' not in line or len(line) < 200:
                continue
            try:
                meta = json.loads(json.loads(line)[0][2])
            except Exception:
                continue
            if isinstance(meta, list) and len(meta) >= 60:
                print("echo:", meta[42], "| family", meta[58], "| variant", meta[59])
                break


if __name__ == "__main__":
    want = sys.argv[1] if len(sys.argv) > 1 else "3.8"
    sid = attach()
    print("attached:", sid)
    hook(sid)
    print("pick:", pick(sid, want))
    print("send:", send(sid, "reply exactly PONG"))
    for i in range(8):
        time.sleep(5)
        if '"wrb.fr"' in (ev("(window.__cap||[]).map(r=>r.resp||'').join('')", sid) or ""):
            break
    report(sid)
