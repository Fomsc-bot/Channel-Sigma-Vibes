"""Retry transient Gemini failures and fall back to a secondary model."""
from __future__ import annotations

import sys
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

TRANSIENT_API_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


def create_gemini_client(api_key):
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=90000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def is_transient(error):
    if isinstance(error, genai_errors.APIError):
        return error.code in {500, 502, 503, 504}
    return isinstance(error, (httpx.TransportError, TimeoutError, ConnectionError))


def parse_api_keys(api_keys):
    keys = []
    for key in str(api_keys or "").splitlines():
        key = key.strip()
        if key and key not in keys:
            keys.append(key)
    if not keys:
        raise ValueError("Set GEMINI_API_KEY to one or more newline-separated API keys")
    return keys


def is_key_rejected(error):
    if not isinstance(error, genai_errors.APIError):
        return False
    if error.code in {401, 403, 429}:
        return True
    details = str(error).casefold()
    return error.code == 400 and any(
        phrase in details for phrase in ("invalid api key", "api key not valid", "api_key_invalid")
    )


def safe_error_message(error, api_keys):
    message = str(error)
    for key in api_keys:
        message = message.replace(key, "[REDACTED]")
    return message


def generate_content_with_fallback(api_keys, model_name, fallback_model, contents, config):
    keys = parse_api_keys(api_keys)
    models = [model_name]
    if fallback_model and fallback_model != model_name:
        models.append(fallback_model)

    last_error = None
    for key_index, key in enumerate(keys, start=1):
        client = create_gemini_client(key)
        key_rejected = False
        for model in models:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                    return response, model
                except Exception as error:
                    last_error = error
                    if is_key_rejected(error):
                        key_rejected = True
                        break
                    if not is_transient(error):
                        raise RuntimeError(
                            f"Gemini request failed: {safe_error_message(error, keys)}"
                        ) from error
                    if attempt + 1 < MAX_ATTEMPTS:
                        delay = 2 ** (attempt + 1)
                        print(
                            f"Transient Gemini error for {model} "
                            f"(attempt {attempt + 1}/{MAX_ATTEMPTS}); retrying in {delay}s.",
                            file=sys.stderr,
                        )
                        time.sleep(delay)
                    elif model != models[-1]:
                        print(
                            f"Gemini {model} remains unavailable; trying {models[-1]}.",
                            file=sys.stderr,
                        )
            if key_rejected:
                break
        if key_rejected and key_index < len(keys):
            print(
                f"Gemini rejected API key {key_index}/{len(keys)}; trying the next key.",
                file=sys.stderr,
            )

    raise RuntimeError(
        f"Gemini request failed for {len(keys)} API key(s) and models "
        f"{', '.join(models)}: {safe_error_message(last_error, keys)}"
    ) from last_error
