from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    role: UserRole = UserRole.collaborator
    # Optional link to the calendar profile this login belongs to.
    collaborator_id: Optional[int] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None


class PasswordChange(BaseModel):
    """Self-service change: the current password proves it is really them."""
    current_password: str
    new_password: str = Field(min_length=12)


class PasswordReset(BaseModel):
    """Admin resetting someone else's password — no current password needed."""
    new_password: str = Field(min_length=12)


class UserWithCollaborator(UserOut):
    collaborator_id: Optional[int] = None
    collaborator_name: Optional[str] = None
