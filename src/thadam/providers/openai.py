"""OpenAI Responses generation with explicit API-key or ChatGPT-plan access.

Requires the optional ``ai`` extra. No implicit provider or billing fallback,
agent tools, repository inspection, or network retries are configured.
"""

from __future__ import annotations

import json
import math
import os
import time

from thadam.generation import INSTRUCTIONS, GenerationResult, validate_request
from thadam.providers.credentials import CredentialStore

API = "https://api.openai.com/v1"
ISSUER = "https://auth.openai.com"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
USAGE_URL = "https://chatgpt.com/#settings/Usage"
LIMIT = 4 * 1024 * 1024


def dependencies():
    try:
        import httpx
        import jwt
    except ImportError as error:
        raise ValueError(
            "Install the optional AI extra: python -m pip install -e '.[ai]'"
        ) from error
    return httpx, jwt


class ProviderError(ValueError):
    """An actionable sanitized provider error; never includes remote error text."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def provider_error(code: object = None, status: int = 0) -> ProviderError:
    if (
        code
        in (
            "subscription_sharing_usage_limit_exceeded",
            "subscription_sharing_usage_unavailable",
            "rate_limit_exceeded",
            "insufficient_quota",
        )
        or status == 429
    ):
        return ProviderError(
            "usage_limit",
            "Usage limit reached. Manage ChatGPT usage or your API billing, then explicitly try again. Your drafts are preserved.",
        )
    if (
        code
        in (
            "subscription_sharing_user_not_eligible",
            "subscription_sharing_not_enabled",
            "insufficient_scope",
        )
        or status == 403
    ):
        return ProviderError(
            "not_eligible",
            "This account or workspace has not enabled eligible plan/model access. Reconnect with permission or explicitly choose API-key access.",
        )
    if status == 401 or code in ("invalid_grant", "invalid_api_key"):
        return ProviderError(
            "authentication",
            "Connection expired or was rejected. Reconnect the selected account or API key.",
        )
    return ProviderError(
        "provider_failed",
        "The provider could not complete this request. Check your selected model and connection, then explicitly try again.",
    )


def check_response(response) -> None:
    if response.is_success:
        return
    code = None
    try:
        error = response.json().get("error", {})
        code = error.get("code") if isinstance(error, dict) else error
    except (ValueError, AttributeError):
        pass
    raise provider_error(code, response.status_code)


def client():
    httpx, _ = dependencies()
    return httpx.Client(
        timeout=httpx.Timeout(45, connect=15), follow_redirects=False, trust_env=False
    )


def token_grant(http, payload: dict) -> dict:
    response = http.post(TOKEN_URL, data=payload)
    check_response(response)
    try:
        data = response.json()
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("access_token"), str)
            or not data["access_token"]
            or data.get("token_type", "Bearer").lower() != "bearer"
            or type(data.get("expires_in")) not in (int, float)
            or not math.isfinite(data["expires_in"])
            or data["expires_in"] <= 0
        ):
            raise ValueError
        if "scope" in data and not isinstance(data["scope"], str):
            raise ValueError
        for name in ("refresh_token", "id_token"):
            if name in data and (not isinstance(data[name], str) or not data[name]):
                raise ValueError
        return data
    except (ValueError, AttributeError) as error:
        raise ProviderError(
            "invalid_response", "The sign-in response was invalid. Reconnect."
        ) from error


def access_token(connection: str, store: CredentialStore, *, api_key: str | None = None) -> str:
    """Resolve only the selected billing path and serialize rotating-token refresh."""
    if connection not in ("api_key", "chatgpt"):
        raise ValueError("Choose api_key or chatgpt access")
    if connection == "api_key" and api_key is not None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ProviderError("not_connected", "Supply a non-empty API key")
        return api_key
    with store.locked():
        data = store.read()
        if connection == "api_key":
            key = api_key or data.get("api_key") or os.environ.get("OPENAI_API_KEY")
            if not isinstance(key, str) or not key.strip():
                raise ProviderError(
                    "not_connected", "Connect an OpenAI API key or set OPENAI_API_KEY"
                )
            return key
        account = data.get("chatgpt")
        if not isinstance(account, dict):
            raise ProviderError(
                "not_connected", "Continue with ChatGPT to connect your subscription"
            )
        if PLAN_SCOPE not in account.get("scopes", []):
            raise ProviderError(
                "plan_disabled",
                "Signed in, but ChatGPT plan usage is not enabled. Reconnect and authorize plan usage.",
            )
        if account.get("expires_at", 0) <= time.time() + 60:
            if not account.get("refresh_token"):
                raise provider_error(status=401)
            httpx, _ = dependencies()
            try:
                with client() as http:
                    refreshed = token_grant(
                        http,
                        {
                            "grant_type": "refresh_token",
                            "client_id": account["client_id"],
                            "refresh_token": account["refresh_token"],
                            "resource": API,
                        },
                    )
            except httpx.HTTPError as error:
                raise ProviderError(
                    "network",
                    "Could not refresh the ChatGPT connection. Check your network or reconnect.",
                ) from error
            account.update(
                access_token=refreshed["access_token"],
                expires_at=time.time() + refreshed["expires_in"],
                refresh_token=refreshed.get("refresh_token", account["refresh_token"]),
            )
            if "scope" in refreshed:
                account["scopes"] = refreshed["scope"].split()
            data["chatgpt"] = account
            store.write(data)
            if PLAN_SCOPE not in account["scopes"]:
                raise ProviderError(
                    "plan_disabled", "ChatGPT plan permission is unavailable. Reconnect."
                )
        return account["access_token"]


def connection_status(store: CredentialStore | None = None) -> dict:
    """Return public connection metadata, never keys or OAuth credentials."""
    store = store or CredentialStore()
    try:
        dependencies()
        available = True
    except ValueError:
        available = False
    with store.locked():
        data = store.read()
    account = data.get("chatgpt", {})
    return {
        "available": available,
        "api_key": bool(data.get("api_key") or os.environ.get("OPENAI_API_KEY")),
        "api_key_environment": bool(os.environ.get("OPENAI_API_KEY")),
        "chatgpt": bool(account),
        "plan_enabled": PLAN_SCOPE in account.get("scopes", []),
        "email": account.get("email"),
        "plan_notice_ack": account.get("plan_notice_ack", False),
        "usage_url": USAGE_URL,
    }


def connect_api_key(key: str, store: CredentialStore | None = None) -> None:
    """Verify a user-supplied key with the model catalog before saving it privately."""
    if not isinstance(key, str) or not key.strip() or any(c.isspace() for c in key):
        raise ValueError("Supply an API key without whitespace")
    store = store or CredentialStore()
    list_models("api_key", store=store, api_key=key)
    with store.locked():
        data = store.read()
        data["api_key"] = key
        store.write(data)


def list_models(
    connection: str, *, store: CredentialStore | None = None, api_key: str | None = None
) -> list[dict]:
    """Fetch the selected account's current catalog without generating content."""
    httpx, _ = dependencies()
    token = access_token(connection, store or CredentialStore(), api_key=api_key)
    try:
        with client() as http:
            response = http.get(API + "/models", headers={"Authorization": "Bearer " + token})
        check_response(response)
        raw = response.json()
        if connection == "chatgpt":
            return [
                {"id": x["slug"], "name": x["display_name"]}
                for x in raw["models"]
                if x.get("visibility") == "list"
            ]
        return [{"id": x["id"], "name": x["id"]} for x in raw["data"]]
    except httpx.HTTPError as error:
        raise ProviderError(
            "network", "Could not load models. Check your network and reconnect if needed."
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ProviderError):
            raise
        raise ProviderError(
            "invalid_response", "The model catalog was invalid. Try refreshing models."
        ) from error


def response_events(response):
    """Bound bytes before line decoding and require complete SSE event boundaries."""
    total, buffer, block = 0, b"", []
    started = time.monotonic()
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > LIMIT:
            raise ProviderError(
                "response_too_large",
                "Generation exceeded the 4 MiB response limit. Request fewer suggestions.",
            )
        if time.monotonic() - started > 300:
            raise ProviderError(
                "generation_timeout",
                "Generation exceeded five minutes. Try a smaller request explicitly.",
            )
        buffer += chunk
        while b"\n" in buffer:
            raw_line, buffer = buffer.split(b"\n", 1)
            line = raw_line.rstrip(b"\r").decode("utf-8")
            if line.startswith("data:"):
                block.append(line[5:].strip())
            elif not line and block:
                raw, block = "\n".join(block), []
                if raw != "[DONE]":
                    event = json.loads(raw)
                    if not isinstance(event, dict):
                        raise ValueError("Invalid stream event")
                    yield event


class OpenAIProvider:
    """Generate proposals with an explicit connection and account-selected model."""

    def __init__(
        self,
        *,
        connection: str,
        model: str,
        store: CredentialStore | None = None,
        api_key: str | None = None,
    ):
        if (
            connection not in ("api_key", "chatgpt")
            or not isinstance(model, str)
            or not model.strip()
        ):
            raise ValueError("Choose an explicit connection and model")
        self.connection, self.model = connection, model
        self.store, self.api_key = store or CredentialStore(), api_key

    def generate(self, request: dict) -> GenerationResult:
        context = validate_request(request)
        httpx, _ = dependencies()
        token = access_token(self.connection, self.store, api_key=self.api_key)
        payload = {
            "model": self.model,
            "instructions": INSTRUCTIONS,
            "input": [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
            "store": False,
            "stream": True,
            "text": {"format": {"type": "json_object"}},
        }
        completed = None
        try:
            with client() as http:
                with http.stream(
                    "POST",
                    API + "/responses",
                    headers={"Authorization": "Bearer " + token},
                    json=payload,
                ) as response:
                    if not response.is_success:
                        response.read()
                        check_response(response)
                    for event in response_events(response):
                        kind = event.get("type")
                        if kind in ("response.failed", "error"):
                            failure = event.get("response", event).get("error", {})
                            raise provider_error(failure.get("code"))
                        if kind == "response.incomplete":
                            raise ProviderError(
                                "incomplete",
                                "Generation was incomplete. Request fewer suggestions and try again.",
                            )
                        if kind == "response.completed":
                            completed = event["response"]
            if completed is None or completed.get("status") != "completed":
                raise ProviderError(
                    "interrupted",
                    "Generation ended without completion. No suggestions were accepted; try again explicitly.",
                )
            texts = []
            for output in completed.get("output", []):
                if output.get("type") != "message":
                    continue
                for part in output.get("content", []):
                    if part.get("type") == "refusal":
                        raise ProviderError(
                            "refused",
                            "The provider declined this request. Revise the selected context and try again.",
                        )
                    if part.get("type") == "output_text":
                        texts.append(part["text"])
            from thadam._json import _invalid_constant, _unique_object

            parsed = json.loads(
                "".join(texts), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
            )
            if not isinstance(parsed, dict) or parsed.keys() != {"candidates"}:
                raise ValueError("Invalid generation envelope")
            return GenerationResult(
                parsed["candidates"],
                "openai_" + self.connection,
                completed.get("model") or self.model,
                completed.get("id"),
                completed.get("usage"),
            )
        except httpx.HTTPError as error:
            raise ProviderError(
                "network",
                "Generation could not finish over the network. Your existing drafts are preserved. Try again explicitly.",
            ) from error
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            if isinstance(error, ProviderError):
                raise
            raise ProviderError(
                "invalid_response",
                "The provider returned malformed suggestions. Your existing drafts are preserved. Revise the context or model and try again.",
            ) from error
