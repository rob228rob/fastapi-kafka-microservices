from datetime import datetime

from pydantic import BaseModel, Field
from typing import Optional, List


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = Field(None, max_length=100)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    disabled: bool
    roles: List[str]

    class Config:
        orm_mode = True

class UsersResponse(BaseModel):
    users: List[UserOut]

class MovieResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    s3_key: str
    created_at: datetime

    class Config:
        orm_mode = True

class MovieUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

    class Config:
        orm_mode = True