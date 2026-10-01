"""
Thin wrapper around the Gemini client.

Keeping this in one place means the model name, API key handling, and SDK
choice can all change without touching interpreter.py or nl_to_sql.py.

Needs GEMINI_API_KEY (or GOOGLE_API_KEY) set in the environment.
"""

import os

from google import genai

# Gemini's model lineup moves fast and old versions get sunset on a
# schedule -- "gemini-flash-latest" is Google's rolling alias that always
# points at their current best Flash model, so this doesn't quietly break
# the day a pinned version is retired. Pin a specific version instead by
# setting GEMINI_MODEL, e.g. GEMINI_MODEL=gemini-3.1-flash-lite.
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

_client = None


class GeminiConfigError(RuntimeError):
    """Raised when no usable API key is available."""


def get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise GeminiConfigError(
            "No Gemini API key found. Set GEMINI_API_KEY (or GOOGLE_API_KEY) "
            "in your environment -- see .env.example, then restart the app."
        )

    _client = genai.Client(api_key=api_key)
    return _client


def reset_client_for_tests() -> None:
    """Test-only hook so each test gets a fresh client/mocking state."""
    global _client
    _client = None
