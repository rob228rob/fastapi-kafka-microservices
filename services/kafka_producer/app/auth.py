# app/auth.py

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from passlib.context import CryptContext
import os
import logging

# Настройка логирования
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,  # Установите DEBUG для более подробных логов
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Секретный ключ для JWT
SECRET_KEY = os.getenv("SECRET_KEY", "your-default-secret-key")  # Замените на свой секретный ключ
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# Настройка контекста для хэширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Pydantic-модели
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

# Псевдоданные пользователей (замените на реальную базу данных)
fake_users_db = {
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "hashed_password": pwd_context.hash("secret"),
        "disabled": False,
    }
}

def verify_password(plain_password, hashed_password):
    result = pwd_context.verify(plain_password, hashed_password)
    logger.debug(f"Verifying password: '{plain_password}' against hashed: '{hashed_password}' -> {result}")
    return result

def get_password_hash(password):
    hashed = pwd_context.hash(password)
    logger.debug(f"Hashed password: '{password}' -> '{hashed}'")
    return hashed

def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        logger.debug(f"User '{username}' found in database.")
        return UserInDB(**user_dict)
    logger.debug(f"User '{username}' not found in database.")
    return None

def authenticate_user(db, username: str, password: str):
    user = get_user(db, username)
    if not user:
        logger.warning(f"Authentication failed: User '{username}' not found.")
        return False
    if not verify_password(password, user.hashed_password):
        logger.warning(f"Authentication failed: Incorrect password for user '{username}'.")
        return False
    logger.info(f"User '{username}' authenticated successfully.")
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.info(f"Access token created for user: '{data.get('sub')}' with expiration at {expire}.")
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    logger.debug(f"Decoding token: '{token}'")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверные учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            logger.warning("Token does not contain 'sub'.")
            raise credentials_exception
        token_data = TokenData(username=username)
        logger.debug(f"Token decoded successfully: {token_data}")
    except JWTError as e:
        logger.error(f"JWTError occurred during token decoding: {e}")
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        logger.warning(f"User '{token_data.username}' not found after token decoding.")
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        logger.warning(f"User '{current_user.username}' is disabled.")
        raise HTTPException(status_code=400, detail="Пользователь не активен")
    logger.debug(f"User '{current_user.username}' is active.")
    return current_user
