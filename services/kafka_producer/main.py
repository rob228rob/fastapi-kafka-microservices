# main.py
import logging
import os
from datetime import timedelta
from typing import Dict

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from passlib.handlers.bcrypt import bcrypt
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    get_current_active_user,
    User,
    admin_required,
)
from app.minio.minio_service import MinioClientWrapper  # Изменено
from app.repositories.movie_repository import create_movie
from app.repositories.user_repository import get_all_users, get_db, create_user, assign_roles_to_user
from app.producer import send_user_stat_to_kafka
from app.repositories.user_repository import Base, engine
import uvicorn

logger = logging.getLogger("app.main")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)

app = FastAPI()  # Создаём объект app на уровне модуля

# Инициализация базы данных
try:
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")
except OperationalError as e:
    logger.error(f"Failed to initialize database: {e}")

# Инициализация MinIO клиента при старте приложения
@app.on_event("startup")
async def startup_event():
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio123")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio123")
    MINIO_BUCKET = os.getenv("MINIO_BUCKET", "movies")

    try:
        app.state.minio_client = MinioClientWrapper(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            bucket_name=MINIO_BUCKET
        )
        logger.info("MinIO клиент инициализирован.")
    except Exception as e:
        logger.error(f"Не удалось инициализировать MinIO клиент: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось инициализировать хранилище."
        )

@app.post("/register", response_model=Token)
async def register_user(
    username: str,
    password: str,
    full_name: str,
    roles: str = "user",  # По умолчанию роль "user"
    db: Session = Depends(get_db)
):
    logger.info(f"Registering new user: '{username}'")
    try:
        user = create_user(db, username=username, password_hash=bcrypt.hash(password), full_name=full_name)
        assign_roles_to_user(db, user.id, roles)
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username, "id": user.id, "roles": user.roles},
            expires_delta=access_token_expires,
        )
        logger.info(f"User '{username}' registered successfully.")
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.error(f"Failed to register user '{username}': {e}")
        raise HTTPException(status_code=400, detail="Failed to register user")

@app.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    logger.info(f"Received authentication request for user: '{form_data.username}'")
    user = authenticate_user(form_data.username, form_data.password)

    if not user:
        logger.warning(f"Authentication failed for user: '{form_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учетные данные",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "id": user.id, "roles": user.roles},
        expires_delta=access_token_expires,
    )
    logger.info(f"User '{user.username}' obtained access token.")
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/send/")
async def send_to_kafka(
    message: Dict, current_user: User = Depends(get_current_active_user)
):
    logger.info(f"User '{current_user.username}' is attempting to send message to Kafka: {message}")
    try:
        send_user_stat_to_kafka(message)
        logger.info(f"Message successfully sent to Kafka by user '{current_user.username}': {message}")
        return {"status": "success", "message": "Message sent to Kafka"}
    except Exception as e:
        logger.error(f"Failed to send message to Kafka: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/users")
async def get_users(limit: int, current_user: User = Depends(admin_required)):
    users = get_all_users(get_db(), limit=limit)
    # Предполагается, что вы хотите вернуть список пользователей
    return {"users": users}

@app.post("/upload_movie")
async def upload_movie(
        title: str,
        description: str,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    minio_client: MinioClientWrapper = app.state.minio_client
    s3_key = f"{current_user.id}/{file.filename}"

    # Сохраняем файл локально временно
    file_path = f"/tmp/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())  # Сделано асинхронным

    try:
        minio_client.upload_movie(s3_key, file_path)

        # Добавляем мета-информацию о фильме в БД
        movie = create_movie(db, title=title, description=description, s3_key=s3_key)

        return {"status": "success", "movie_id": movie.id}
    finally:
        os.remove(file_path)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )
