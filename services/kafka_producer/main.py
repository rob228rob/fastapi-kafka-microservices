# app/main.py

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict
from datetime import timedelta
import logging

from app.auth import (
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    get_current_active_user,
    User,
    fake_users_db,
)
from app.producer import send_message

# Настройка логирования
logger = logging.getLogger("app.main")
logging.basicConfig(
    level=logging.DEBUG,  # Установите DEBUG для более подробных логов
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

app = FastAPI()

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    logger.info(f"Received authentication request for user: '{form_data.username}'")
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        logger.warning(f"Authentication failed for user: '{form_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учетные данные",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    logger.info(f"User '{user.username}' obtained access token.")
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/send/")
async def send_to_kafka(message: Dict, current_user: User = Depends(get_current_active_user)):
    """
    Endpoint для отправки сообщения в Kafka
    """
    logger.info(f"User '{current_user.username}' is attempting to send message to Kafka: {message}")
    try:
        send_message(message)
        logger.info(f"Message successfully sent to Kafka by user '{current_user.username}': {message}")
        return {"status": "success", "message": "Message sent to Kafka"}
    except Exception as e:
        logger.error(f"Failed to send message to Kafka: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/protected/")
async def protected_route(current_user: User = Depends(get_current_active_user)):
    """
    Пример защищенного маршрута
    """
    logger.info(f"Protected route accessed by user '{current_user.username}'.")
    return {"message": f"Hello, {current_user.username}!"}
