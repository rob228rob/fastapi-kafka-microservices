# src/main.py

import logging
import os
from datetime import timedelta
from typing import Dict

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from passlib.handlers.bcrypt import bcrypt
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy.orm import Session

from movie_router import movie_router
from src.auth import (
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    get_current_active_user,
    User,
)

from src.minio.minio_service import MinioClientWrapper
from src.producer import send_user_stat_to_kafka
from src.repositories.user_repository import (
    BaseDeclaration,
    engine,
    get_db,
    create_user,
    assign_roles_to_user,
    get_user_by_username, assign_role_to_user,
)
from src.streaming.streaming import router as streaming_router
from admin_router import admin_route

from pydantic_models import UserRegister

# from src.admin.admin_router  import router as admin_router  # Импортируйте admin_router

logger = logging.getLogger("src.main")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)

app = FastAPI(
    title="Main Api",
    description="Основной сервис, отвечающий за авторизацию, стриминг и ",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(admin_route)
app.include_router(streaming_router)
app.include_router(movie_router)

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


@app.get("/liveness")
async def health():
    return {"status": "ok", "problems": []}

@app.post("/register", response_model=Token)
async def register_user(user: UserRegister, db: Session = Depends(get_db)):
    logger.info(f"Registering new user: '{user.username}'")
    try:
        existing_user = get_user_by_username(db, user.username)
        if existing_user:
            raise HTTPException(status_code=409, detail="Username already exists")

        hashed_password = bcrypt.hash(user.password)
        new_user = create_user(db,
                               username=user.username,
                               password_hash=hashed_password,
                               full_name=user.full_name)
        assign_role_to_user(db, new_user.id, "user")
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": new_user.username, "id": new_user.id, "roles": [role.name for role in new_user.roles]},
            expires_delta=access_token_expires,
        )
        logger.info(f"User '{user.username}' registered successfully.")
        return {"access_token": access_token, "token_type": "bearer"}
    except IntegrityError as ex:
        logger.error(f"Integrity error occurred: {ex}")
        raise HTTPException(status_code=409, detail="Database integrity error")
    except HTTPException as http_err:
        raise http_err  # Пропустить заранее сгенерированные HTTP исключения
    except Exception as ex:
        logger.error(f"Unexpected error during registration: {type(ex).__name__} - {str(ex)}")
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
