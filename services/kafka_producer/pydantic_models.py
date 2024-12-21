from pydantic import BaseModel, Field
from typing import Optional, List


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = Field(None, max_length=100)
    roles: str = "user"


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