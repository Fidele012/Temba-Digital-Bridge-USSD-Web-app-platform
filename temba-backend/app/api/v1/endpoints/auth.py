"""
Auth endpoints:
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
POST /auth/forgot-password
POST /auth/reset-password
POST /auth/change-password
GET  /auth/verify-email/{token}
"""
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from jose import JWTError
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, write_audit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.db.redis import (
    delete_refresh_token,
    delete_reset_otp,
    get_reset_otp,
    get_stored_refresh_token,
    store_refresh_token,
    store_reset_otp,
)
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    ChangePasswordRequest,
    CompleteProfileRequest,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    SetPinRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserCreate, UserPublic
from app.services.notification_service import send_email_background, send_sms_background

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_TTL = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400


# ── Password-reset helpers ────────────────────────────────────────────────────

def _looks_like_email(s: str) -> bool:
    return "@" in s


def _phone_variants(phone: str) -> list[str]:
    """Return common storage formats of the phone to match against DB rows."""
    p = re.sub(r"[\s\-]", "", phone)
    variants: set[str] = {p}
    if p.startswith("+250") and len(p) >= 12:
        variants.update({"0" + p[4:], "250" + p[4:]})
    elif p.startswith("250") and len(p) == 12:
        variants.update({"+" + p, "0" + p[3:]})
    elif p.startswith("0") and len(p) == 10:
        variants.update({"+250" + p[1:], "250" + p[1:]})
    return list(variants)


def _ussd_email_variants(phone: str) -> list[str]:
    """Return all @ussd.temba.rw email addresses that could correspond to this phone."""
    digits_only = re.sub(r"[^\d]", "", phone)
    candidates: set[str] = set()
    for v in _phone_variants(phone):
        stripped = re.sub(r"[^\d]", "", v)
        candidates.add(f"{stripped}@ussd.temba.rw")
    candidates.add(f"{digits_only}@ussd.temba.rw")
    return list(candidates)


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    normalized_email = body.email.lower().strip()
    result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    verification_token = str(uuid4())
    user = User(
        email=normalized_email,
        phone=body.phone,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        province=body.province,
        district=body.district,
        sector=body.sector,
        cell=body.cell,
        village=body.village,
        verification_token=verification_token,
    )
    db.add(user)
    await db.flush()

    await write_audit(db, request, "user.register", "user", str(user.id))

    background_tasks.add_task(
        send_email_background,
        to=user.email,
        subject="Verify your Temba account",
        template="verify_email",
        context={"name": user.full_name, "token": verification_token},
    )
    return user


@router.get("/verify-email/{token}", response_model=MessageResponse)
async def verify_email(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(select(User).where(User.verification_token == token))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token")
    user.is_verified = True
    user.verification_token = None
    return {"message": "Email verified successfully"}


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    user: User | None = None

    if body.phone and body.pin:
        # ── Phone + PIN path (USSD-registered users logging into web) ──────────
        # Try USSD-style synthetic email accounts first
        for email_candidate in _ussd_email_variants(body.phone):
            row = (await db.execute(select(User).where(User.email == email_candidate))).scalar_one_or_none()
            if row:
                user = row
                break
        # Fall back to web users who have phone field set
        if user is None:
            variants = _phone_variants(body.phone)
            user = (await db.execute(
                select(User).where(or_(*[User.phone == v for v in variants]))
            )).scalar_one_or_none()

        if not user or not user.ussd_pin_hash:
            await write_audit(db, request, "auth.login_failed", "user", extra={"phone": body.phone}, status_code=401)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phone number not found or PIN not set",
            )
        if not verify_password(body.pin, user.ussd_pin_hash):
            await write_audit(db, request, "auth.login_failed", "user", extra={"phone": body.phone}, status_code=401)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect PIN")

    else:
        # ── Email + Password path (web-registered users) ────────────────────────
        result = await db.execute(select(User).where(func.lower(User.email) == body.email.lower().strip()))
        user = result.scalar_one_or_none()
        if not user or not verify_password(body.password, user.hashed_password):
            await write_audit(db, request, "auth.login_failed", "user", extra={"email": str(body.email)}, status_code=401)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id, user.role.value)
    await store_refresh_token(str(user.id), refresh_token, _REFRESH_TTL)

    user.last_login = datetime.now(timezone.utc)
    await write_audit(db, request, "auth.login", "user", str(user.id), actor=user, status_code=200)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        data = decode_refresh_token(body.refresh_token)
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user_id = data["sub"]
    stored = await get_stored_refresh_token(user_id)
    if stored != body.refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid or expired")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    new_access = create_access_token(user.id, user.role.value)
    new_refresh = create_refresh_token(user.id, user.role.value)
    await store_refresh_token(str(user.id), new_refresh, _REFRESH_TTL)

    return {
        "access_token": new_access,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    await delete_refresh_token(str(current_user.id))
    await write_audit(db, request, "auth.logout", "user", str(current_user.id), actor=current_user)
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    identifier = body.identifier.strip()
    user: User | None = None

    if _looks_like_email(identifier):
        result = await db.execute(select(User).where(func.lower(User.email) == identifier.lower()))
        user = result.scalar_one_or_none()
        channel = "email"
    else:
        variants = _phone_variants(identifier)
        result = await db.execute(
            select(User).where(or_(*[User.phone == v for v in variants]))
        )
        user = result.scalar_one_or_none()
        channel = "sms"

    if user:
        otp = f"{random.randint(0, 999_999):06d}"
        await store_reset_otp(str(user.id), otp)
        # Always log the OTP so it is visible in docker logs during development
        log.info(
            "Password reset OTP generated",
            user_id=str(user.id),
            channel=channel,
            otp=otp,  # visible in: docker logs temba-backend-api-1 | grep otp
        )

        if channel == "email":
            background_tasks.add_task(
                send_email_background,
                to=user.email,
                subject="Your Temba password reset code",
                template="reset_password",
                context={"name": user.full_name, "code": otp},
            )
        else:
            dest_phone = user.phone or identifier
            background_tasks.add_task(
                send_sms_background,
                to=dest_phone,
                message=(
                    f"Temba Digital Bridge: Your password reset code is {otp}. "
                    "It expires in 15 minutes. Do not share it with anyone."
                ),
            )

    # Always 200 — prevents account enumeration
    return {"message": "If that account exists, a 6-digit reset code has been sent."}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: PasswordResetConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    identifier = body.identifier.strip()
    user: User | None = None

    if _looks_like_email(identifier):
        result = await db.execute(select(User).where(func.lower(User.email) == identifier.lower()))
        user = result.scalar_one_or_none()
    else:
        variants = _phone_variants(identifier)
        result = await db.execute(
            select(User).where(or_(*[User.phone == v for v in variants]))
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code",
        )

    stored_otp = await get_reset_otp(str(user.id))
    if not stored_otp or stored_otp != body.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code. Please request a new one.",
        )

    user.hashed_password = hash_password(body.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await delete_reset_otp(str(user.id))
    await delete_refresh_token(str(user.id))
    log.info("Password reset successful", user_id=str(user.id))
    return {"message": "Password reset successfully"}


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(body.new_password)
    await delete_refresh_token(str(current_user.id))
    return {"message": "Password changed successfully"}


@router.get("/check-phone")
async def check_phone(
    phone: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Returns whether a phone is already registered (USSD or web). Used by signup form."""
    variants = _phone_variants(phone)
    for email_candidate in _ussd_email_variants(phone):
        row = (await db.execute(select(User.id).where(User.email == email_candidate))).scalar_one_or_none()
        if row:
            return {"registered": True, "is_ussd": True}
    row = (await db.execute(
        select(User.id).where(or_(*[User.phone == v for v in variants]))
    )).scalar_one_or_none()
    if row:
        return {"registered": True, "is_ussd": False}
    return {"registered": False, "is_ussd": False}


@router.post("/complete-profile", response_model=MessageResponse)
async def complete_profile(
    body: CompleteProfileRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """USSD-registered users set a real email + web password on first web login."""
    if not current_user.email.endswith("@ussd.temba.rw"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile is already complete",
        )
    normalized = body.email.lower().strip()
    existing = (await db.execute(
        select(User).where(func.lower(User.email) == normalized)
    )).scalar_one_or_none()
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    current_user.email = normalized
    current_user.hashed_password = hash_password(body.password)
    current_user.is_verified = True  # authenticated via PIN — treat as verified
    await write_audit(db, request, "auth.complete_profile", "user", str(current_user.id), actor=current_user)
    return {"message": "Profile completed successfully"}


@router.post("/set-pin", response_model=MessageResponse)
async def set_pin(
    body: SetPinRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Set or update the 4-digit USSD PIN for the current user."""
    current_user.ussd_pin_hash = hash_password(body.pin)
    await write_audit(db, request, "auth.set_pin", "user", str(current_user.id), actor=current_user)
    return {"message": "USSD PIN set successfully"}
