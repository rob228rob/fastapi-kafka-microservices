# main.py
import logging
import os
from datetime import timedelta
from typing import Dict

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from passlib.handlers.bcrypt import bcrypt
from sqlalchemy.exc import OperationalError, IntegrityError
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
from app.producer import send_user_stat_to_kafka
from app.repositories.movie_repository import create_movie
from app.repositories.user_repository import BaseDeclaration, engine
from app.repositories.user_repository import get_all_users, get_db, create_user, assign_roles_to_user, \
    get_user_by_username
from pydantic_models import UserRegister

import app.repositories.movie_repository
import app.repositories.user_repository

from streaming import router as streaming_router

logger = logging.getLogger("app.main")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)

app = FastAPI(
    title="Ваше приложение",
    description="Описание вашего API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)  # Создаём объект app на уровне модуля

# Инициализация базы данных
try:
    logger.info("Initializing database...")
    BaseDeclaration.metadata.create_all(bind=engine)
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
        minio_client = MinioClientWrapper(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            bucket_name=MINIO_BUCKET
        )
        app.state.minio_client = minio_client
        logger.info("MinIO клиент инициализирован.")
    except Exception as e:
        logger.error(f"Не удалось инициализировать MinIO клиент: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось инициализировать хранилище."
        )


def get_minio_client() -> MinioClientWrapper:
    return app.state.minio_client

# Подключение роутера из streaming.py
app.include_router(streaming_router)

@app.get("/liveness")
async def health():
    return {"status": "ok", "problems": "0"}


@app.post("/register", response_model=Token)
async def register_user(user: UserRegister, db: Session = Depends(get_db)):
    logger.info(f"Registering new user: '{user.username}'")
    try:
        existing_user = get_user_by_username(db, user.username)
        if existing_user:
            raise HTTPException(status_code=409, detail="Username already exists")

        hashed_password = bcrypt.hash(user.password)
        new_user = create_user(db, username=user.username, password_hash=hashed_password, full_name=user.full_name)
        assign_roles_to_user(db, new_user.id, user.roles.split(","))  # если `roles` — строка с запятыми
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": new_user.username, "id": new_user.id, "roles": [role.name for role in new_user.roles]},
            expires_delta=access_token_expires,
        )
        logger.info(f"User '{user.username}' registered successfully.")
        return {"access_token": access_token, "token_type": "bearer"}
    except IntegrityError as e:
        logger.error(f"Database integrity error: {e}")
        raise HTTPException(status_code=409, detail="Username already exists")
    except Exception as e:
        logger.error(f"Failed to register user '{user.username}': {e}")
        raise HTTPException(status_code=400, detail="Failed to register user")


@app.post("/login", response_model=Token)
async def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: Session = Depends(get_db)
):
    logger.info(f"Received authentication request for user: '{form_data.username}'")
    user = authenticate_user(form_data.username, form_data.password, db)

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


from pydantic_models import UserOut, UsersResponse

@app.get("/admin/users", response_model=UsersResponse)
async def get_users(
        limit: int,
        current_user: User = Depends(admin_required),
        db: Session = Depends(get_db)
):
    users = get_all_users(db, limit=limit)

    users_out = [
        UserOut(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            disabled=user.disabled,
            roles=[role.name for role in user.roles]
        )
        for user in users
    ]

    return {"users": users_out}


@app.post("/admin/upload_movie")
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
        f.write(await file.read())

    try:
        minio_client.upload_movie(s3_key, file_path)

        # Добавляем мета-информацию о фильме в БД
        movie = create_movie(db, title=title, description=description, s3_key=s3_key)

        return {"status": "success", "movie_id": movie.id}
    finally:
        os.remove(file_path)
