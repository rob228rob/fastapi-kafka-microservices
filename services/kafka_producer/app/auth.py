# app/auth.py
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from passlib.context import CryptContext
import os
import logging

from sqlalchemy.orm import Session

from .repositories.user_repository import get_user_by_username, get_user_by_id, get_db

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)

SECRET_KEY = os.getenv("SECRET_KEY", "weuid9wiedijewe9dwdew9due9udewd-ewdh7gdweidhneuidew7832idnjknj32uhukn3ejmijdij3d3id")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    id: Optional[int] = None
    roles: List[str] = []

class User(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    roles: List[str] = []

class UserInDB(User):
    hashed_password: str

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(username: str, db: Session) -> Optional[UserInDB]:
    user = get_user_by_username(db, username)
    if user:
        return UserInDB(
            id=user.id,
            username=user.username,
            hashed_password=user.hashed_password,
            full_name=user.full_name,
            disabled=user.disabled,
            roles=[role.name for role in user.roles]
        )
    return None

def authenticate_user(username: str, password: str, db: Session):
    user = get_user(username, db)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверные учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        roles: List[str] = payload.get("roles", [])
        if username is None or user_id is None:
            raise credentials_exception
        token_data = TokenData(username=username, id=user_id, roles=roles)
        logger.info(f"token data: {token_data}")
    except JWTError:
        raise credentials_exception

    user = get_user_by_id(db, token_data.id)
    if not user:
        raise credentials_exception
    if user:
        return UserInDB(
            id=user.id,
            username=user.username,
            hashed_password=user.hashed_password,
            full_name=user.full_name,
            disabled=user.disabled,
            roles=[role.name for role in user.roles]
        )

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Пользователь не активен")
    return current_user


def admin_required(current_user: User = Depends(get_current_active_user)):
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён: требуется роль администратора"
        )
    return current_user

def any_roles_required(roles: List[str], current_user: User = Depends(get_current_active_user)):
    # Проверяем, содержит ли пользователь хотя бы одну из необходимых ролей
    if not any(r in current_user.roles for r in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Доступ запрещён: требуется одна из ролей: {roles}"
        )
    return current_user
