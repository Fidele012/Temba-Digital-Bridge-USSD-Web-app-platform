from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class LoginRequest(BaseModel):
    # Email + password path (web-registered users)
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=1, max_length=128)
    # Phone + PIN path (USSD-registered users logging into web)
    phone: str | None = None
    pin: str | None = None

    @model_validator(mode='after')
    def check_credentials(self) -> 'LoginRequest':
        has_email_auth = bool(self.email and self.password)
        has_phone_auth = bool(self.phone and self.pin)
        if not has_email_auth and not has_phone_auth:
            raise ValueError("Provide either (email + password) or (phone + pin)")
        return self


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    identifier: str  # email address or phone number


class PasswordResetConfirm(BaseModel):
    identifier: str   # same value used to request the code
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("code")
    @classmethod
    def code_digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Reset code must be 6 digits")
        return v

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class CompleteProfileRequest(BaseModel):
    """USSD-registered users upgrading to a full web account."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class SetPinRequest(BaseModel):
    """Set or update the 4-digit USSD PIN on any account."""
    pin: str = Field(min_length=4, max_length=4)

    @field_validator("pin")
    @classmethod
    def digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("PIN must be exactly 4 digits")
        return v
