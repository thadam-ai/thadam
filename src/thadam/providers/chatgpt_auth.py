"""Loopback OAuth/PKCE sign-in for open-source ChatGPT plan usage."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

from thadam.providers.credentials import CredentialStore
from thadam.providers.openai import (
    API,
    ISSUER,
    PLAN_SCOPE,
    ProviderError,
    client,
    dependencies,
    token_grant,
)


class ChatGPTSignIn:
    """Own one short-lived, single-use browser sign-in, with no project credentials.

    The callback listener binds 127.0.0.1 only. ID-token signatures, issuer,
    audience, expiry, subject and nonce are validated before replacing a connection.
    Call close() on application shutdown or cancellation. Status never exposes tokens.
    """

    def __init__(self, store: CredentialStore | None = None):
        self.store = store or CredentialStore()
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.state = "idle"
        self.error = None
        self.pending = None

    def start(self) -> str:
        dependencies()
        self.close()
        with self.lock:
            with self.store.locked():
                saved = self.store.read()
                host_id = self.store.host_id(saved)
                account = saved.get("chatgpt", {})
            self.pending = {
                "state": secrets.token_urlsafe(32),
                "nonce": secrets.token_urlsafe(32),
                "verifier": secrets.token_urlsafe(64),
                "expires": time.monotonic() + 300,
                "client_id": account.get("client_id"),
                "subject": account.get("subject"),
            }
            owner = self

            class Callback(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup()
                    self.connection.settimeout(10)

                def log_message(self, *_args):
                    pass

                def do_GET(self):
                    target = urlsplit(self.path)
                    if target.path != "/auth/callback":
                        self.send_error(404)
                        return
                    try:
                        params = parse_qs(target.query, keep_blank_values=True, strict_parsing=True)
                        if any(len(values) != 1 for values in params.values()):
                            raise ValueError("Invalid callback parameters")
                        owner.complete({key: value[0] for key, value in params.items()})
                        message, status = "Connected. Return to Thadam to continue.", 200
                    except (ValueError, OSError):
                        message, status = (
                            "Sign-in could not complete. Return to Thadam for the next step.",
                            400,
                        )
                    self.send_response(status)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header(
                        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
                    )
                    self.end_headers()
                    self.wfile.write(message.encode())

            self.server = HTTPServer(("127.0.0.1", 0), Callback)
            self.server.timeout = 0.2
            self.pending["redirect_uri"] = (
                f"http://127.0.0.1:{self.server.server_port}/auth/callback"
            )
            self.state, self.error = "pending", None
            parameters = {
                "client_id": account.get("client_id") or "dynamic_agent_client",
                "ext_agent_host_id": host_id,
                "response_type": "code",
                "redirect_uri": self.pending["redirect_uri"],
                "scope": "openid profile email offline_access resource.invoke " + PLAN_SCOPE,
                "resource": API,
                "state": self.pending["state"],
                "nonce": self.pending["nonce"],
                "code_challenge_method": "S256",
                "code_challenge": base64.urlsafe_b64encode(
                    hashlib.sha256(self.pending["verifier"].encode()).digest()
                )
                .decode()
                .rstrip("="),
            }
            if not account:
                parameters["agent_name_hint"] = "Thadam"
            self.thread = threading.Thread(target=self._listen, args=(self.server,), daemon=True)
            self.thread.start()
            return ISSUER + "/api/accounts/authorize?" + urlencode(parameters)

    def _listen(self, server):
        while self.state == "pending" and self.server is server:
            if self.pending and time.monotonic() > self.pending["expires"]:
                self.state, self.error, self.pending = (
                    "error",
                    "Sign-in expired. Continue with ChatGPT again.",
                    None,
                )
                break
            server.handle_request()
        server.server_close()

    def complete(self, parameters: dict) -> None:
        """Consume a matching transaction once, then verify OpenAI's response."""
        httpx, jwt = dependencies()
        with self.lock:
            pending = self.pending
            if not pending or self.state != "pending" or time.monotonic() > pending["expires"]:
                raise ValueError("Sign-in expired or already used")
            if not hmac.compare_digest(
                str(parameters.get("state", "")).encode(), pending["state"].encode()
            ):
                raise ValueError("Sign-in state did not match")
            self.pending = None
            try:
                if parameters.get("error"):
                    raise ProviderError(
                        "denied", "Sign-in was declined. Continue with ChatGPT when you are ready."
                    )
                identifier = parameters.get("client_id") or pending["client_id"]
                if (
                    not isinstance(identifier, str)
                    or not identifier.startswith("oaiapp_")
                    or not parameters.get("code")
                ):
                    raise ValueError("Registration did not return a client ID or code")
                if pending["client_id"] and identifier != pending["client_id"]:
                    raise ValueError("The selected account registration changed")
                with client() as http:
                    tokens = token_grant(
                        http,
                        {
                            "grant_type": "authorization_code",
                            "client_id": identifier,
                            "code": parameters["code"],
                            "code_verifier": pending["verifier"],
                            "redirect_uri": pending["redirect_uri"],
                            "resource": API,
                        },
                    )
                    keys_response = http.get(ISSUER + "/.well-known/jwks.json")
                    keys_response.raise_for_status()
                    header = jwt.get_unverified_header(tokens["id_token"])
                    if header.get("alg") not in ("RS256", "ES256"):
                        raise ValueError("Unsupported identity signature")
                    key = next(
                        key
                        for key in keys_response.json()["keys"]
                        if key.get("kid") == header.get("kid")
                    )
                    claims = jwt.decode(
                        tokens["id_token"],
                        jwt.PyJWK.from_dict(key).key,
                        algorithms=[header["alg"]],
                        audience=identifier,
                        issuer=ISSUER,
                        options={"require": ["sub", "exp", "iat", "nonce"]},
                    )
                if (
                    not isinstance(claims["sub"], str)
                    or not claims["sub"]
                    or not isinstance(claims["nonce"], str)
                    or not hmac.compare_digest(claims["nonce"], pending["nonce"])
                ):
                    raise ValueError("Identity or nonce did not match")
                if pending["subject"] and claims["sub"] != pending["subject"]:
                    raise ValueError("Disconnect before switching ChatGPT accounts")
                if claims.get("azp") is not None and claims["azp"] != identifier:
                    raise ValueError("Identity authorized party did not match")
                if "at_hash" in claims:
                    expected_hash = (
                        base64.urlsafe_b64encode(
                            hashlib.sha256(tokens["access_token"].encode("ascii")).digest()[:16]
                        )
                        .decode()
                        .rstrip("=")
                    )
                    if not isinstance(claims["at_hash"], str) or not hmac.compare_digest(
                        claims["at_hash"], expected_hash
                    ):
                        raise ValueError("Identity access-token hash did not match")
                if (
                    isinstance(claims["aud"], list)
                    and len(claims["aud"]) > 1
                    and claims.get("azp") != identifier
                ):
                    raise ValueError("Identity authorized party did not match")
                scopes = tokens.get("scope", "").split()
                with self.store.locked():
                    saved = self.store.read()
                    active = saved.get("chatgpt", {})
                    if (active.get("client_id"), active.get("subject")) != (
                        pending["client_id"],
                        pending["subject"],
                    ):
                        raise ValueError("Connection changed during sign-in; start again")
                    saved["chatgpt"] = {
                        "client_id": identifier,
                        "subject": claims["sub"],
                        "email": claims.get("email")
                        if isinstance(claims.get("email"), str)
                        else None,
                        "access_token": tokens["access_token"],
                        "refresh_token": tokens.get("refresh_token"),
                        "id_token": tokens["id_token"],
                        "plan_notice_ack": active.get("plan_notice_ack", False),
                        "scopes": scopes,
                        "expires_at": time.time() + tokens["expires_in"],
                    }
                    self.store.write(saved)
                self.state = "connected"
                self.error = (
                    None
                    if PLAN_SCOPE in scopes
                    else "Signed in, but ChatGPT plan usage was not authorized. Reconnect and enable plan usage."
                )
            except (Exception,) as error:
                self.state = "error"
                self.error = (
                    str(error)
                    if isinstance(error, ProviderError)
                    else "Sign-in could not be verified. Continue with ChatGPT again."
                )
                raise ValueError(self.error) from error

    def status(self) -> dict:
        return {"state": self.state, "error": self.error}

    def close(self) -> None:
        with self.lock:
            self.state = "idle"
            self.pending = None
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
        if self.server:
            self.server.server_close()
        self.server, self.thread = None, None
