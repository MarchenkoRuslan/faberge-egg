from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class AuthSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class RegisterRequest(AuthSchema):
    display_name: str = Field(alias="displayName", min_length=1, max_length=255)
    email: EmailStr
    password: str
    confirm_password: str = Field(alias="confirmPassword")
    terms_agree: bool = Field(alias="termsAgree")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @model_validator(mode="after")
    def validate_registration(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password confirmation does not match")
        if not self.terms_agree:
            raise ValueError("You must accept Terms of Use")
        return self


class RegisterResponse(AuthSchema):
    id: int
    email: str
    display_name: str | None = Field(default=None, alias="displayName")
    is_email_verified: bool = Field(alias="isEmailVerified")
    requires_email_verification: bool = Field(alias="requiresEmailVerification")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LoginRequest(AuthSchema):
    email: EmailStr
    password: str

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"email": "user@example.com", "password": "securepassword"}]},
        populate_by_name=True,
    )


class TokenResponse(AuthSchema):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    token_type: str = "bearer"
    expires_in: int = Field(alias="expiresIn")
    refresh_expires_in: int = Field(alias="refreshExpiresIn")


class EmailVerifyRequest(AuthSchema):
    email: EmailStr


class EmailVerifyConfirmRequest(AuthSchema):
    token: str


class TokenValidateRequest(AuthSchema):
    token: str


class TokenValidateResponse(AuthSchema):
    valid: bool = True


class RefreshRequest(AuthSchema):
    refresh_token: str = Field(alias="refreshToken")


class LogoutRequest(AuthSchema):
    refresh_token: str = Field(alias="refreshToken")


class PasswordForgotRequest(AuthSchema):
    email: EmailStr


class PasswordResetRequest(AuthSchema):
    token: str
    password: str
    confirm_password: str = Field(alias="confirmPassword")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @model_validator(mode="after")
    def validate_confirm(self) -> "PasswordResetRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password confirmation does not match")
        return self


class MessageResponse(AuthSchema):
    message: str


class MeResponse(AuthSchema):
    id: int
    email: str
    display_name: str | None = Field(default=None, alias="displayName")
    is_email_verified: bool = Field(alias="isEmailVerified")
    created_at: str = Field(alias="createdAt")
