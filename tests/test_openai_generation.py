"""Controlled Responses/OAuth checks; no credentials or live provider calls."""

# ruff: noqa: E402

import base64
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest

httpx = pytest.importorskip("httpx")
jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.test_generation import candidate, context
from thadam.generation import suggest_cases
from thadam.providers import chatgpt_auth, openai
from thadam.providers.chatgpt_auth import ChatGPTSignIn
from thadam.providers.credentials import CredentialStore
from thadam.providers.openai import API, ISSUER, PLAN_SCOPE, OpenAIProvider, ProviderError


@pytest.fixture
def store(tmp_path):
    return CredentialStore(tmp_path / "credentials")


def transport(monkeypatch, handler):
    monkeypatch.setattr(
        openai, "client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(chatgpt_auth, "client", openai.client)


def save_account(store, **changes):
    with store.locked():
        data = store.read()
        data["chatgpt"] = {
            "client_id": "oaiapp_fixture",
            "subject": "user",
            "email": "fixture@example.com",
            "access_token": "plan-token",
            "refresh_token": "refresh",
            "expires_at": time.time() + 3600,
            "scopes": [PLAN_SCOPE],
            **changes,
        }
        store.write(data)


def stream(events):
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content="".join("data: " + json.dumps(event) + "\n\n" for event in events),
    )


def completed(text=None):
    return {
        "type": "response.completed",
        "response": {
            "id": "response",
            "model": "fixture-model",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": text or json.dumps({"candidates": [candidate()]}),
                        }
                    ],
                }
            ],
            "usage": {"input_tokens": 0, "output_tokens": 12},
        },
    }


@pytest.mark.parametrize("connection", ["api_key", "chatgpt"])
def test_explicit_billing_and_complete_stream(monkeypatch, store, connection):
    save_account(store)
    monkeypatch.setenv("OPENAI_API_KEY", "api-secret")
    seen = []

    def handle(request):
        seen.append(request)
        return stream([{"type": "response.output_text.delta", "delta": "partial"}, completed()])

    transport(monkeypatch, handle)
    data = suggest_cases(
        OpenAIProvider(connection=connection, model="selected", store=store), context()
    )
    assert len(data["candidates"]) == 1
    assert data["generation"]["usage"]["input_tokens"] == 0
    request = seen[0]
    assert request.url == API + "/responses"
    assert request.headers["authorization"] == "Bearer " + (
        "plan-token" if connection == "chatgpt" else "api-secret"
    )
    body = json.loads(request.content)
    assert body["model"] == "selected"
    assert body["store"] is False and body["stream"] is True
    assert "tools" not in body
    assert len(seen) == 1


@pytest.mark.parametrize(
    "events,code",
    [
        ([], "interrupted"),
        ([{"type": "response.incomplete"}], "incomplete"),
        ([completed("not JSON")], "invalid_response"),
        ([completed('{"candidates":[],"candidates":[]}')], "invalid_response"),
        (
            [
                {
                    "type": "response.failed",
                    "response": {
                        "error": {
                            "code": "subscription_sharing_usage_limit_exceeded",
                            "message": "secret",
                        }
                    },
                }
            ],
            "usage_limit",
        ),
        (
            [
                completed(),
                {
                    "type": "response.failed",
                    "response": {"error": {"code": "subscription_sharing_usage_unavailable"}},
                },
            ],
            "usage_limit",
        ),
    ],
)
def test_stream_failures_never_publish_partial_output(monkeypatch, store, events, code):
    transport(monkeypatch, lambda request: stream(events))
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(
            connection="api_key", model="selected", store=store, api_key="secret"
        ).generate(context())
    assert caught.value.code == code
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "authentication"),
        (403, "not_eligible"),
        (429, "usage_limit"),
        (500, "provider_failed"),
    ],
)
def test_http_failures_are_sanitized_without_retry(monkeypatch, store, status, code):
    calls = []

    def fail(request):
        calls.append(True)
        return httpx.Response(status, json={"error": {"message": "api-secret and private prompt"}})

    transport(monkeypatch, fail)
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(
            connection="api_key", model="selected", store=store, api_key="api-secret"
        ).generate(context())
    assert caught.value.code == code
    assert "api-secret" not in str(caught.value)
    assert calls == [True]


def test_missing_plan_permission_does_not_fall_back_to_available_api_key(monkeypatch, store):
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-use")
    with pytest.raises(ProviderError, match="Continue with ChatGPT"):
        openai.access_token("chatgpt", store)
    save_account(store, scopes=[])
    with pytest.raises(ProviderError, match="not enabled"):
        openai.access_token("chatgpt", store)


def test_account_specific_model_catalog(monkeypatch, store):
    save_account(store)
    transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "models": [
                    {"slug": "allowed", "display_name": "Allowed", "visibility": "list"},
                    {"slug": "hidden", "visibility": "hidden"},
                ]
            },
        ),
    )
    assert openai.list_models("chatgpt", store=store) == [{"id": "allowed", "name": "Allowed"}]
    transport(
        monkeypatch, lambda request: httpx.Response(200, json={"data": [{"id": "api-model"}]})
    )
    openai.connect_api_key("saved-secret", store)
    status = openai.connection_status(store)
    assert status["api_key"] and status["chatgpt"]
    assert "secret" not in json.dumps(status) and "plan-token" not in json.dumps(status)
    assert (store.root / "connections.json").stat().st_mode & 0o077 == 0
    store.disconnect("api_key")
    assert not openai.connection_status(store)["api_key"]


def test_refresh_is_serialized_and_rotated_tokens_replaced_together(monkeypatch, store):
    save_account(store, expires_at=0)
    calls = []

    def handle(request):
        calls.append(parse_qs(request.content.decode()))
        time.sleep(0.03)
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
                "scope": PLAN_SCOPE,
            },
        )

    transport(monkeypatch, handle)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _: openai.access_token("chatgpt", store), range(2)))
    assert tokens == ["new-access", "new-access"]
    assert len(calls) == 1
    assert calls[0]["client_id"] == ["oaiapp_fixture"]
    assert "scope" not in calls[0]
    with store.locked():
        assert store.read()["chatgpt"]["refresh_token"] == "new-refresh"


class Listener:
    """No sockets needed to verify authorization protocol and callback handling."""

    server_port = 1455
    timeout = 0.2

    def __init__(self, address, handler):
        assert address == ("127.0.0.1", 0)

    def handle_request(self):
        time.sleep(0.005)

    def server_close(self):
        pass


@pytest.fixture
def signin(monkeypatch, store):
    monkeypatch.setattr(chatgpt_auth, "HTTPServer", Listener)
    flow = ChatGPTSignIn(store)
    yield flow
    flow.close()


def mock_identity(
    monkeypatch, signin, *, claims_changes=None, scope=PLAN_SCOPE, invalid_signature=False
):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048) if invalid_signature else key
    )
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public["kid"] = "fixture"
    calls = []
    claims = {
        "sub": "user",
        "iss": ISSUER,
        "aud": "oaiapp_fixture",
        "iat": time.time(),
        "exp": time.time() + 3600,
        "nonce": signin.pending["nonce"],
        "email": "fixture@example.com",
        **(claims_changes or {}),
    }
    identity = jwt.encode(claims, signing, algorithm="RS256", headers={"kid": "fixture"})

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "access_token": "private-token",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                    "id_token": identity,
                    "scope": scope,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(200, json={"keys": [public]})

    transport(monkeypatch, handler)
    return calls


def test_initial_login_pkce_verified_callback_and_replay_rejected(monkeypatch, signin):
    url = signin.start()
    query = {key: value[0] for key, value in parse_qs(urlsplit(url).query).items()}
    assert query["client_id"] == "dynamic_agent_client" and query["agent_name_hint"] == "Thadam"
    assert query["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"
    assert query["code_challenge"] == base64.urlsafe_b64encode(
        hashlib.sha256(signin.pending["verifier"].encode()).digest()
    ).decode().rstrip("=")
    calls = mock_identity(monkeypatch, signin)
    callback = {"state": query["state"], "code": "code", "client_id": "oaiapp_fixture"}
    signin.complete(callback)
    assert signin.status() == {"state": "connected", "error": None}
    with pytest.raises(ValueError, match="already used"):
        signin.complete(callback)
    grant = parse_qs(calls[0].content.decode())
    assert grant["client_id"] == ["oaiapp_fixture"] and grant["redirect_uri"] == [
        query["redirect_uri"]
    ]
    assert "private-token" not in json.dumps(signin.status())
    url = signin.start()
    returning = parse_qs(urlsplit(url).query)
    assert returning["client_id"] == ["oaiapp_fixture"]
    assert returning["ext_agent_host_id"] == [query["ext_agent_host_id"]]
    assert "agent_name_hint" not in returning


@pytest.mark.parametrize(
    "claims_changes",
    [
        {"nonce": "wrong"},
        {"iss": "https://attacker.invalid"},
        {"aud": "wrong"},
        {"exp": 1},
        {"sub": ""},
        {"azp": "wrong"},
        {"at_hash": "wrong"},
    ],
)
def test_invalid_identity_does_not_save_credentials(monkeypatch, signin, claims_changes):
    signin.start()
    state = signin.pending["state"]
    mock_identity(monkeypatch, signin, claims_changes=claims_changes)
    with pytest.raises(ValueError, match="verified"):
        signin.complete({"state": state, "code": "code", "client_id": "oaiapp_fixture"})
    assert not openai.connection_status(signin.store)["chatgpt"]


def test_invalid_signature_and_denied_consent(monkeypatch, signin):
    signin.start()
    state = signin.pending["state"]
    mock_identity(monkeypatch, signin, invalid_signature=True)
    with pytest.raises(ValueError):
        signin.complete({"state": state, "code": "code", "client_id": "oaiapp_fixture"})
    signin.start()
    with pytest.raises(ValueError, match="declined"):
        signin.complete({"state": signin.pending["state"], "error": "access_denied"})
    assert not openai.connection_status(signin.store)["chatgpt"]


def test_missing_plan_scope_retains_identity_without_inference_permission(monkeypatch, signin):
    signin.start()
    state = signin.pending["state"]
    mock_identity(monkeypatch, signin, scope="openid email")
    signin.complete({"state": state, "code": "code", "client_id": "oaiapp_fixture"})
    assert openai.connection_status(signin.store)["chatgpt"]
    assert not openai.connection_status(signin.store)["plan_enabled"]
    with pytest.raises(ProviderError, match="not enabled"):
        openai.access_token("chatgpt", signin.store)


def test_bad_state_and_account_switch_never_replace_active_identity(monkeypatch, signin):
    save_account(signin.store)
    signin.start()
    with pytest.raises(ValueError, match="state"):
        signin.complete({"state": "wrong", "code": "code"})
    state = signin.pending["state"]
    mock_identity(monkeypatch, signin, claims_changes={"sub": "different"})
    with pytest.raises(ValueError):
        signin.complete({"state": state, "code": "code"})
    with signin.store.locked():
        assert signin.store.read()["chatgpt"]["subject"] == "user"


def test_signin_expiry_and_cancellation_reject_callback(signin):
    signin.start()
    state = signin.pending["state"]
    signin.pending["expires"] = 0
    with pytest.raises(ValueError, match="expired"):
        signin.complete({"state": state})
    signin.close()
    with pytest.raises(ValueError):
        signin.complete({"state": state})


def test_stream_byte_budget_is_checked_before_json_parsing(monkeypatch, store):
    monkeypatch.setattr(openai, "LIMIT", 20)
    transport(monkeypatch, lambda request: stream([completed()]))
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(
            connection="api_key", model="selected", store=store, api_key="secret"
        ).generate(context())
    assert caught.value.code == "response_too_large"


def test_explicit_sdk_api_key_needs_no_user_configuration_directory(monkeypatch, store):
    monkeypatch.setattr(
        store, "locked", lambda: (_ for _ in ()).throw(AssertionError("No configuration needed"))
    )
    assert openai.access_token("api_key", store, api_key="explicit-key") == "explicit-key"
