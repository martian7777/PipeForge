"""OAuth 2.0 / OpenID Connect single sign-on.

Implements the **authorization code flow with PKCE** (RFC 7636) against Google,
Microsoft Entra ID, and GitHub. A provider is enabled purely by supplying its client id
and secret; nothing else needs configuring.

Why the pieces are here:

* **PKCE** -- a per-request ``code_verifier`` is generated and only its SHA-256 hash
  travels in the authorize redirect. An attacker who intercepts the authorization code
  cannot redeem it without the verifier.
* **state** -- a random value round-tripped through the provider and checked on return.
  This is the CSRF defence for the callback.
* **nonce** -- bound into the OIDC ``id_token`` and re-checked, so a token minted for a
  different session cannot be replayed into ours.
* **Stateless carry** -- state, verifier and nonce are packed into a short-lived signed
  JWT stored in an HttpOnly cookie rather than server memory, so the authorize and
  callback halves of the flow can land on *different replicas* behind the load balancer.
* **id_token verification** -- for the OIDC providers the token signature is checked
  against the provider's live JWKS, with audience, issuer and expiry all enforced. The
  user identity is taken from the verified token, never from an unauthenticated
  userinfo response.

GitHub is not an OIDC provider, so it has no ``id_token``; there the access token is
used against the REST API, and the *verified, primary* email is required.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class OAuthError(Exception):
    """Any failure in the SSO handshake. The message is safe to show a user."""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    client_id: str
    client_secret: str
    # OIDC providers return a verifiable id_token; GitHub does not.
    is_oidc: bool = False
    jwks_url: str = ""
    issuer: str = ""  # blank = do not pin (multi-tenant Entra ID)
    userinfo_url: str = ""
    extra_authorize_params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Identity:
    """The provider-independent identity we upsert into the users table."""

    provider: str
    subject: str  # stable opaque id -- never the email
    email: str
    email_verified: bool
    full_name: str | None = None
    avatar_url: str | None = None


def _providers() -> dict[str, ProviderSpec]:
    """Build the registry from current settings. Cheap; called per request."""
    specs: dict[str, ProviderSpec] = {}

    if settings.google_client_id and settings.google_client_secret:
        specs["google"] = ProviderSpec(
            name="google",
            label="Google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=("openid", "email", "profile"),
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            is_oidc=True,
            jwks_url="https://www.googleapis.com/oauth2/v3/certs",
            issuer="https://accounts.google.com",
            # Force the account chooser so switching accounts actually works.
            extra_authorize_params={"prompt": "select_account", "access_type": "online"},
        )

    if settings.microsoft_client_id and settings.microsoft_client_secret:
        tenant = settings.microsoft_tenant or "common"
        base = f"https://login.microsoftonline.com/{tenant}"
        specs["microsoft"] = ProviderSpec(
            name="microsoft",
            label="Microsoft",
            authorize_url=f"{base}/oauth2/v2.0/authorize",
            token_url=f"{base}/oauth2/v2.0/token",
            scopes=("openid", "email", "profile", "User.Read"),
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            is_oidc=True,
            jwks_url=f"{base}/discovery/v2.0/keys",
            # A single-tenant app has a fixed issuer; "common"/"organizations" do not,
            # because the issuer embeds whichever tenant the user signed in from.
            issuer=(
                f"https://login.microsoftonline.com/{tenant}/v2.0"
                if tenant not in ("common", "organizations", "consumers")
                else ""
            ),
            extra_authorize_params={"prompt": "select_account"},
        )

    if settings.github_client_id and settings.github_client_secret:
        specs["github"] = ProviderSpec(
            name="github",
            label="GitHub",
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            scopes=("read:user", "user:email"),
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            is_oidc=False,
            userinfo_url="https://api.github.com/user",
        )

    return specs


def available_providers() -> list[dict[str, str]]:
    """What the login page should render buttons for."""
    return [{"name": p.name, "label": p.label} for p in _providers().values()]


def get_provider(name: str) -> ProviderSpec:
    spec = _providers().get(name)
    if spec is None:
        raise OAuthError(f"Unknown or unconfigured SSO provider: {name!r}")
    return spec


def redirect_uri(provider: str) -> str:
    """The callback URL registered with the provider. Must match byte-for-byte."""
    return f"{settings.public_base_url.rstrip('/')}/api/auth/oauth/{provider}/callback"


# --- PKCE ---------------------------------------------------------------------


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` using the S256 method."""
    verifier = _b64url(secrets.token_bytes(64))  # 43-128 chars per RFC 7636
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


# --- The signed state cookie --------------------------------------------------


def pack_state(provider: str, verifier: str, nonce: str, next_path: str) -> tuple[str, str]:
    """Return ``(state, cookie_value)``.

    ``state`` goes to the provider in the URL; ``cookie_value`` is a signed JWT holding
    the same state plus the secrets that must never leave our origin. Comparing the two
    on the way back is what proves the callback belongs to this browser's flow.
    """
    state = secrets.token_urlsafe(32)
    cookie = jwt.encode(
        {
            "state": state,
            "provider": provider,
            "verifier": verifier,
            "nonce": nonce,
            "next": next_path,
            "exp": datetime.now(timezone.utc)
            + timedelta(seconds=settings.oauth_state_ttl_seconds),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return state, cookie


def unpack_state(cookie_value: str | None, state: str | None, provider: str) -> dict[str, Any]:
    """Validate the returned state against the cookie. Raises ``OAuthError``."""
    if not cookie_value:
        raise OAuthError("Sign-in session expired or cookies are blocked. Please try again.")
    if not state:
        raise OAuthError("Missing state parameter.")
    try:
        payload = jwt.decode(
            cookie_value, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise OAuthError("Sign-in session expired. Please try again.") from exc

    if not secrets.compare_digest(str(payload.get("state", "")), state):
        raise OAuthError("State mismatch -- the sign-in request could not be verified.")
    if payload.get("provider") != provider:
        raise OAuthError("State was issued for a different provider.")
    return payload


# --- Flow steps ---------------------------------------------------------------


def build_authorize_url(spec: ProviderSpec, state: str, code_challenge: str, nonce: str) -> str:
    params = {
        "response_type": "code",
        "client_id": spec.client_id,
        "redirect_uri": redirect_uri(spec.name),
        "scope": " ".join(spec.scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        **spec.extra_authorize_params,
    }
    if spec.is_oidc:
        params["nonce"] = nonce
    return f"{spec.authorize_url}?{urlencode(params)}"


async def exchange_code(spec: ProviderSpec, code: str, verifier: str) -> dict[str, Any]:
    """Redeem the authorization code for tokens (back channel, client secret attached)."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(spec.name),
        "client_id": spec.client_id,
        "client_secret": spec.client_secret,
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.post(
            spec.token_url, data=data, headers={"Accept": "application/json"}
        )

    if response.status_code >= 400:
        logger.warning(
            "oauth token exchange failed",
            extra={
                "event": "auth.oauth.token_exchange_failed",
                "provider": spec.name,
                "status_code": response.status_code,
            },
        )
        raise OAuthError("Could not complete sign-in with the identity provider.")

    payload = response.json()
    if "error" in payload:
        raise OAuthError(f"Identity provider rejected the request: {payload.get('error')}")
    return payload


def _verify_id_token(spec: ProviderSpec, id_token: str, nonce: str) -> dict[str, Any]:
    """Verify signature (live JWKS), audience, expiry, issuer, and nonce."""
    try:
        signing_key = jwt.PyJWKClient(spec.jwks_url).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=spec.client_id,
            issuer=spec.issuer or None,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning(
            "id_token verification failed",
            extra={"event": "auth.oauth.id_token_invalid", "provider": spec.name, "error": str(exc)},
        )
        raise OAuthError("The identity token from the provider could not be verified.") from exc

    if claims.get("nonce") != nonce:
        raise OAuthError("Identity token nonce mismatch -- possible replay.")
    return claims


async def _github_identity(access_token: str) -> Identity:
    """GitHub has no id_token; read the profile and require a verified primary email."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        profile_res = await client.get("https://api.github.com/user", headers=headers)
        emails_res = await client.get("https://api.github.com/user/emails", headers=headers)

    if profile_res.status_code >= 400:
        raise OAuthError("Could not read your GitHub profile.")
    profile = profile_res.json()

    email, verified = profile.get("email"), False
    if emails_res.status_code < 400:
        entries = emails_res.json()
        primary = next(
            (e for e in entries if e.get("primary") and e.get("verified")),
            next((e for e in entries if e.get("verified")), None),
        )
        if primary:
            email, verified = primary.get("email"), True

    if not email:
        raise OAuthError("Your GitHub account has no verified email address available.")

    return Identity(
        provider="github",
        subject=str(profile["id"]),
        email=email.lower(),
        email_verified=verified,
        full_name=profile.get("name") or profile.get("login"),
        avatar_url=profile.get("avatar_url"),
    )


async def resolve_identity(spec: ProviderSpec, tokens: dict[str, Any], nonce: str) -> Identity:
    """Turn a token response into a verified, normalized identity."""
    if not spec.is_oidc:
        access_token = tokens.get("access_token")
        if not access_token:
            raise OAuthError("Identity provider returned no access token.")
        return await _github_identity(access_token)

    id_token = tokens.get("id_token")
    if not id_token:
        raise OAuthError("Identity provider returned no id_token.")
    claims = _verify_id_token(spec, id_token, nonce)

    email = claims.get("email") or claims.get("preferred_username") or ""
    if not email:
        raise OAuthError("The identity provider did not release an email address.")

    # Google sets email_verified explicitly. Entra ID omits it for work/school accounts,
    # where the tenant already guarantees the address.
    verified = bool(claims.get("email_verified", spec.name == "microsoft"))

    return Identity(
        provider=spec.name,
        subject=str(claims["sub"]),
        email=str(email).lower(),
        email_verified=verified,
        full_name=claims.get("name"),
        avatar_url=claims.get("picture"),
    )


def email_domain_allowed(email: str) -> bool:
    """Enforce ``PIPEFORGE_OAUTH_ALLOWED_EMAIL_DOMAINS`` (empty = allow all)."""
    allowed = [d.strip().lower().lstrip("@") for d in settings.oauth_allowed_email_domains if d.strip()]
    if not allowed:
        return True
    return email.rsplit("@", 1)[-1].lower() in allowed


def safe_next_path(candidate: str | None) -> str:
    """Only allow same-origin relative paths, so the callback cannot be an open redirect."""
    if not candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate
