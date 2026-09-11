"""
Groq API key.

Resolution order:

1. The key the user pasted into Settings (``Config.groq_api_key``), so anyone
   whose key expires can fix it from the app without a rebuild.
2. ``core/ai_config_local.py`` — untracked, for local development.
3. The ``GROQ_API_KEY`` environment variable.
4. The placeholder below, which the release workflow overwrites with the real
   key from the GitHub secret when building the installer.

The local file is git-ignored on purpose: the key must never reach the repo,
and this module IS tracked.
"""

import os

# Overwritten by .github/workflows/release.yml when building for production.
GROQ_API_KEY = "PUT_YOUR_GROQ_API_KEY_HERE"

if not GROQ_API_KEY or GROQ_API_KEY.startswith("PUT_YOUR"):
    try:
        from core.ai_config_local import GROQ_API_KEY as _LOCAL_KEY
    except ImportError:
        pass
    else:
        if _LOCAL_KEY:
            GROQ_API_KEY = _LOCAL_KEY

if not GROQ_API_KEY or GROQ_API_KEY.startswith("PUT_YOUR"):
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", GROQ_API_KEY)


def get_groq_api_key() -> str:
    """Resolve the Groq key to use right now, preferring the user's own.

    Read on every call (not cached at import time) so a key pasted into
    Settings takes effect immediately, without restarting the app.
    """
    try:
        from config.settings import Config
        user_key = Config.load().groq_api_key.strip()
    except Exception:
        user_key = ''
    return user_key or GROQ_API_KEY
