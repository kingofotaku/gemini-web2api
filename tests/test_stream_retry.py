"""The stream path must retry a dropped connection, but only while nothing
has reached the client; once bytes are out, retrying would duplicate output.

Run: python tests/test_stream_retry.py
"""
import importlib.util
import json
import os
import sys

import httpx

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('gw2a_under_test', os.path.join(REPO, 'gemini_web2api.py'))
m = importlib.util.module_from_spec(spec)
sys.modules['gw2a_under_test'] = m
spec.loader.exec_module(m)
m.load_config(os.path.join(REPO, 'config.json'))


def frame(text):
    """A minimal valid wrb.fr line (inner list kept under 60 so the routing
    check is skipped)."""
    inner = [None, ['c_test', 'r_test'], None, None, [[None, [text]]]]
    return json.dumps([['wrb.fr', None, json.dumps(inner), None, None, None, 'generic']]) + '\n'


class FakeStream:
    def __init__(self, lines, fail_before=None):
        self.lines = lines
        self.fail_before = fail_before   # raise before yielding line #n

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_text(self):
        for i, line in enumerate(self.lines):
            if self.fail_before == i:
                raise httpx.RemoteProtocolError('peer closed connection without sending complete message body')
            yield line
        if self.fail_before == len(self.lines):
            raise httpx.RemoteProtocolError('connection dropped at end of stream')


def run(responses):
    """Drive one request through a scripted sequence of stream attempts."""
    calls = []

    def fake_stream(self, method, url, **kw):
        i = len(calls)
        calls.append(i)
        lines, fail_before = responses[min(i, len(responses) - 1)]
        return FakeStream(lines, fail_before)

    real = httpx.Client.stream
    httpx.Client.stream = fake_stream
    out, err = '', None
    try:
        # iterate manually: keep whatever already reached the client, so the
        # "emitted" behaviour can actually be observed
        for delta in m.gemini_stream_generate_iter('hi', 1, 4, None, {80: 1}, 'gemini-3.8-flash'):
            out += delta
    except Exception as e:
        err = e
    finally:
        httpx.Client.stream = real
    return out, err, calls


# 1) dropped before any output → retry is invisible, so it must retry and succeed
out, err, calls = run([([], 0), ([frame('你好')], None)])
assert err is None, err
assert out == '你好', repr(out)
assert len(calls) == 2, calls
print('1/3 retry-after-drop-before-output: OK (attempts=%d)' % len(calls))

# 2) dropped AFTER output reached the client → must NOT retry (no duplicate text)
out, err, calls = run([([frame('你好'), frame('你好世界')], 1)])
assert len(calls) == 1, calls
assert out.startswith('你好'), repr(out)
print('2/3 no-retry-after-output: OK (attempts=%d, out=%r)' % (len(calls), out[:20]))

# 3) keeps failing → retries up to the configured limit, then raises
limit = m.CONFIG['retry_attempts']
out, err, calls = run([([], 0)])
assert len(calls) == limit, (len(calls), limit)
assert err is not None, 'should have raised after exhausting retries'
print('3/3 retries-exhausted-then-raise: OK (attempts=%d, err=%s)' % (len(calls), type(err).__name__))

print('\nall stream-retry checks passed')
