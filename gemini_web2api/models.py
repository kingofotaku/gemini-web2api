"""Model definitions and mapping from Gemini frontend JS source."""

# MODE_CATEGORY enum from 028-6eb337387583.js:
#   1=FAST, 2=THINKING, 3=PRO, 4=AUTO, 5=FAST_DYNAMIC_THINKING, 6=FLASH_LITE
#
# Model routing (verified live 2026-09-25): the request header
# `x-goog-ext-525001261-jspb` decides the served model. Its index 4 is a model
# key that must exist in the account page's id list; indices 14/15 are the
# (family, variant) the backend actually routes on. Payload slot79 alone does
# nothing. See gemini.build_ticket().

MODELS = {
    "gemini-3.8-flash": {
        "mode": 1, "think": 4, "family": 1, "variant": 1,
        "desc": "All-around model (Flash family)",
    },
    "gemini-3.1-pro": {
        "mode": 3, "think": 4, "family": 3, "variant": 1,
        "desc": "Pro model (Advanced subscription required)",
    },
}


def ticket_for(model_name: str):
    """Build the model-selection ticket for a model, or None if none needed.

    The key comes from CONFIG["model_keys"] (per-family account ids captured
    from the account page); a missing key means no ticket is sent, which makes
    upstream serve the account default model.
    """
    from .config import CONFIG
    from .gemini import build_ticket

    cfg = MODELS.get(model_name) or {}
    family = cfg.get("family")
    if not family:
        return None
    key = (CONFIG.get("model_keys") or {}).get(_KEY_KIND.get(family))
    if not key:
        return None
    return build_ticket(key, family, cfg.get("variant", 1))


# Which CONFIG["model_keys"] entry a family uses. Captured from the account
# page; a single key can serve several families (the ticket's 14/15 decide).
_KEY_KIND = {1: "flash", 3: "pro", 6: "lite"}


def resolve_model(model_name: str, default: str = "gemini-3.8-flash"):
    """Resolve model name to (name, mode_id, think_mode, error, extra_fields).

    Unknown model names fall back to default rather than erroring,
    since upstream clients may request arbitrary model identifiers.
    """
    think_override = None
    if "@think=" in model_name:
        model_name, think_str = model_name.rsplit("@think=", 1)
        try:
            think_override = int(think_str)
        except ValueError:
            return None, None, None, f"Invalid think level: {think_str}", None
    cfg = MODELS.get(model_name)
    if not cfg:
        from .gemini import log
        log(f"Unknown model '{model_name}', falling back to '{default}'")
        model_name = default
        cfg = MODELS[default]
    mode_id = cfg["mode"]
    think_mode = think_override if think_override is not None else cfg["think"]
    # slot80 (variant) must reach both the payload and the ticket's index 15 —
    # the contract ties them together, so it is always carried, never absent.
    extra = dict(cfg.get("extra") or {})
    extra[80] = cfg.get("variant", 1)
    return model_name, mode_id, think_mode, None, extra
