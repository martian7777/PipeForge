"""Authentication endpoints.

Three ways in, one way out:

* **Password** -- ``/register`` + ``/login`` (OAuth2 password grant form encoding).
* **SSO** -- ``/oauth/{provider}/authorize`` -> provider -> ``/oauth/{provider}/callback``,
  the authorization code flow with PKCE. See ``app/oauth.py``.
* **Refresh** -- ``/refresh`` rotates a refresh token into a fresh pair.

All of them end at ``_issue_session``, which mints the token pair, sets the HttpOnly
refresh cookie, and writes the audit record.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, oauth
from ..config import settings
from ..db import get_db
from ..logging_config import get_logger
from ..models import OAuthIdentity, RefreshToken, Role, User
from ..ratelimit import limiter
from ..schemas import (
    AuthOptions,
    PasswordChange,
    RefreshRequest,
    SessionOut,
    SsoProvider,
    Token,
    UserCreate,
    UserOut,
)
from ..security import (
    RefreshError,
    create_access_token,
    current_user,
    hash_password,
    issue_refresh_token,
    revoke_all_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_OAUTH_STATE_COOKIE = "pipeforge_oauth_state"


# --- Session plumbing --------------------------------------------------------


def _set_refresh_cookie(response: Response, token: str) -> None:
    """HttpOnly so browser JS can never read it; SameSite blocks cross-site replay.

    Path is scoped to the auth routes, so the token is not attached to ordinary API
    calls -- it only travels where it is actually needed.
    """
    response.set_cookie(
        settings.refresh_cookie_name,
        token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path="/api/auth")


def _issue_session(db: Session, user: User, request: Request, response: Response) -> Token:
    """Mint the token pair for a user who has just proven their identity."""
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    refresh = issue_refresh_token(db, user, request)
    _set_refresh_cookie(response, refresh)
    return Token(
        access_token=create_access_token(user),
        expires_in=settings.access_token_ttl_minutes * 60,
        refresh_token=refresh,
    )


def _initial_role(db: Session, email: str) -> str:
    """Bootstrap: the configured admin email, or the very first account, becomes admin."""
    configured = settings.bootstrap_admin_email.strip().lower()
    if configured:
        return Role.ADMIN if email.lower() == configured else Role.USER
    return Role.ADMIN if db.scalar(select(User.id).limit(1)) is None else Role.USER


# --- Password auth -----------------------------------------------------------


@router.get("/options", response_model=AuthOptions)
def auth_options() -> AuthOptions:
    """Public: which sign-in methods this deployment offers."""
    return AuthOptions(
        password_login_enabled=True,
        providers=[SsoProvider(**p) for p in oauth.available_providers()],
    )


@router.post("/register", response_model=Token, status_code=201)
@limiter.limit(settings.ratelimit_auth)
def register(
    request: Request, response: Response, body: UserCreate, db: Session = Depends(get_db)
) -> Token:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        audit.record(db, audit.REGISTER, request=request, actor_email=email, outcome="failure",
                     reason="email_taken")
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=_initial_role(db, email),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    audit.record(db, audit.REGISTER, request=request, actor=user, role=user.role)
    return _issue_session(db, user, request, response)


@router.post("/login", response_model=Token)
@limiter.limit(settings.ratelimit_auth)
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    # The OAuth2 password form calls it "username"; we treat it as the email.
    email = form.username.lower()
    user = db.scalar(select(User).where(User.email == email))

    if user is None or not verify_password(form.password, user.password_hash):
        # Deliberately identical response for "no such user" and "wrong password" so the
        # endpoint cannot be used to enumerate registered addresses.
        audit.record(db, audit.LOGIN_FAILURE, request=request, actor_email=email,
                     outcome="failure", reason="bad_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        audit.record(db, audit.LOGIN_FAILURE, request=request, actor=user,
                     outcome="failure", reason="inactive")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    audit.record(db, audit.LOGIN_SUCCESS, request=request, actor=user, method="password")
    return _issue_session(db, user, request, response)


@router.post("/refresh", response_model=Token)
@limiter.limit(settings.ratelimit_auth)
def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
) -> Token:
    """Rotate a refresh token into a new pair. Reuse revokes the whole family."""
    token = (body.refresh_token if body else None) or request.cookies.get(
        settings.refresh_cookie_name
    )
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token supplied")

    try:
        access, new_refresh, user = rotate_refresh_token(db, token, request)
    except RefreshError as exc:
        _clear_refresh_cookie(response)
        audit.record(
            db,
            audit.REFRESH_REUSE if exc.reuse_detected else audit.REFRESH_FAILURE,
            request=request,
            outcome="failure",
            reason=str(exc),
        )
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    _set_refresh_cookie(response, new_refresh)
    audit.record(db, audit.REFRESH_SUCCESS, request=request, actor=user)
    return Token(
        access_token=access,
        expires_in=settings.access_token_ttl_minutes * 60,
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    """Revoke the presented refresh token and clear the cookie. Safe to call twice."""
    token = request.cookies.get(settings.refresh_cookie_name)
    if token:
        revoke_refresh_token(db, token, reason="logout")
    _clear_refresh_cookie(response)
    audit.record(db, audit.LOGOUT, request=request)


@router.post("/logout-all", status_code=204)
def logout_all(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    """Sign out every device: revoke all refresh tokens and invalidate access tokens."""
    revoked = revoke_all_for_user(db, user, reason="logout_all")
    _clear_refresh_cookie(response)
    audit.record(db, audit.LOGOUT_ALL, request=request, actor=user, revoked_count=revoked)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.get("/sessions", response_model=list[SessionOut])
def my_sessions(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[RefreshToken]:
    """The caller's live sign-ins, newest first."""
    return list(
        db.scalars(
            select(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .order_by(RefreshToken.issued_at.desc())
        )
    )


@router.post("/password", status_code=204)
@limiter.limit(settings.ratelimit_auth)
def change_password(
    request: Request,
    response: Response,
    body: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    """Change the password and sign out everywhere -- a rotated credential should not
    leave older sessions alive."""
    if not verify_password(body.current_password, user.password_hash):
        audit.record(db, "auth.password.change", request=request, actor=user,
                     outcome="failure", reason="bad_current_password")
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(body.new_password)
    db.commit()
    revoke_all_for_user(db, user, reason="password_changed")
    _clear_refresh_cookie(response)
    audit.record(db, "auth.password.change", request=request, actor=user)


# --- OAuth 2.0 / OIDC single sign-on -----------------------------------------


def _sso_error_redirect(message: str) -> RedirectResponse:
    """Bounce back to the SPA login page with a displayable reason."""
    target = f"{settings.public_base_url.rstrip('/')}/login?{urlencode({'sso_error': message})}"
    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/api/auth")
    return response


@router.get("/oauth/{provider}/authorize")
@limiter.limit(settings.ratelimit_auth)
def oauth_authorize(
    provider: str, request: Request, next: str = "/", db: Session = Depends(get_db)
) -> RedirectResponse:
    """Start the authorization code + PKCE flow by redirecting to the provider."""
    try:
        spec = oauth.get_provider(provider)
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    verifier, challenge = oauth.generate_pkce_pair()
    nonce = oauth.generate_pkce_pair()[0]  # a second high-entropy random value
    state, cookie_value = oauth.pack_state(
        provider, verifier, nonce, oauth.safe_next_path(next)
    )

    audit.record(db, audit.OAUTH_START, request=request, target=provider)

    response = RedirectResponse(
        oauth.build_authorize_url(spec, state, challenge, nonce),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    # The verifier and nonce must survive the round trip without server-side state, so
    # the flow works no matter which replica handles the callback.
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        cookie_value,
        max_age=settings.oauth_state_ttl_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",  # must be lax, not strict: the provider redirects cross-site
        path="/api/auth",
    )
    return response


def _upsert_sso_user(db: Session, identity: oauth.Identity, request: Request) -> User:
    """Find or create the local account behind a verified federated identity."""
    link = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == identity.provider,
            OAuthIdentity.subject == identity.subject,
        )
    )
    now = datetime.now(timezone.utc)

    if link is not None:
        user = db.get(User, link.user_id)
        if user is None:
            raise oauth.OAuthError("The linked account no longer exists.")
        link.last_login_at = now
        link.email = identity.email
        db.commit()
        return user

    # No link yet. Attach to an existing local account with the same address only when
    # the provider asserts the address is verified -- otherwise anyone able to set an
    # unverified email at the provider could take over a local account.
    user = db.scalar(select(User).where(User.email == identity.email))
    if user is not None and not identity.email_verified:
        raise oauth.OAuthError(
            "That email is already registered and the provider has not verified it. "
            "Sign in with your password instead."
        )

    if user is None:
        user = User(
            email=identity.email,
            password_hash=None,  # SSO-only account
            full_name=identity.full_name,
            avatar_url=identity.avatar_url,
            role=_initial_role(db, identity.email),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        audit.record(db, audit.REGISTER, request=request, actor=user,
                     method="sso", provider=identity.provider, role=user.role)
    else:
        user.full_name = user.full_name or identity.full_name
        user.avatar_url = user.avatar_url or identity.avatar_url

    db.add(
        OAuthIdentity(
            user_id=user.id,
            provider=identity.provider,
            subject=identity.subject,
            email=identity.email,
            last_login_at=now,
        )
    )
    db.commit()
    audit.record(db, audit.OAUTH_LINKED, request=request, actor=user, target=identity.provider)
    return user


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Provider redirect target: verify, exchange, upsert, and hand off to the SPA."""
    if error:
        audit.record(db, audit.OAUTH_FAILURE, request=request, target=provider,
                     outcome="failure", reason=error, description=error_description)
        return _sso_error_redirect(error_description or error)

    try:
        spec = oauth.get_provider(provider)
        packed = oauth.unpack_state(request.cookies.get(_OAUTH_STATE_COOKIE), state, provider)
        if not code:
            raise oauth.OAuthError("Provider returned no authorization code.")

        tokens = await oauth.exchange_code(spec, code, packed["verifier"])
        identity = await oauth.resolve_identity(spec, tokens, packed["nonce"])

        if not oauth.email_domain_allowed(identity.email):
            raise oauth.OAuthError("Your email domain is not permitted to sign in here.")

        user = _upsert_sso_user(db, identity, request)
        if not user.is_active:
            raise oauth.OAuthError("This account has been disabled.")

    except oauth.OAuthError as exc:
        audit.record(db, audit.OAUTH_FAILURE, request=request, target=provider,
                     outcome="failure", reason=str(exc))
        return _sso_error_redirect(str(exc))

    audit.record(db, audit.OAUTH_SUCCESS, request=request, actor=user,
                 target=provider, method="sso")

    # Land on the SPA with no tokens in the URL: the refresh cookie is the only thing
    # handed over, and the SPA immediately trades it for an access token via /refresh.
    landing = (
        f"{settings.public_base_url.rstrip('/')}{settings.oauth_post_login_path}"
        f"?{urlencode({'next': packed.get('next', '/')})}"
    )
    response = RedirectResponse(landing, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/api/auth")
    _set_refresh_cookie(response, issue_refresh_token(db, user, request))
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return response
