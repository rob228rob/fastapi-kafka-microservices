# admin_router.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from minio import S3Error
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from src.auth import admin_required, get_current_active_user, User
from src.repositories.movie_repository import create_movie, update_movie, \
    delete_movie, get_movie_by_id
from src.repositories.user_repository import get_all_users, get_db
from pydantic_models import UserOut, UsersResponse, MovieResponse, MovieUpdate

from src.minio.minio_service import MinioClientWrapper
from src.dependencies import get_minio_client

import logging
import os

admin_route = APIRouter(
    prefix="/admin",  # Все маршруты будут начинаться с /admin
    tags=["Admin"],
    dependencies=[Depends(admin_required)],  # Все маршруты требуют роль администратора
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal Server Error"},
        503: {"description": "Service Unavailable"}
    }
)

logger = logging.getLogger("src.admin")

@admin_route.get("/users", response_model=UsersResponse)
async def get_users(
        limit: int = 100,
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

from fastapi import Form

@admin_route.post("/upload_movie", response_model=MovieResponse)
async def upload_movie(
        title: str = Form(...),  # title передается через form-data
        description: str = Form(...),  # description тоже передается через form-data
        file: UploadFile = File(...),  # Файл передается через form-data
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
        minio_client: MinioClientWrapper = Depends(get_minio_client)
):
    s3_key = f"{current_user.id}/{file.filename}"

    # Сохраняем файл локально временно
    file_path = f"/tmp/{file.filename}"
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save file locally: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file locally")

    try:
        minio_client.upload_movie(s3_key, file_path)

        movie = create_movie(db, title=title, description=description, s3_key=s3_key)

        return MovieResponse(
            id=movie.id,
            title=movie.title,
            description=movie.description,
            s3_key=movie.s3_key,
            created_at=movie.created_at
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to upload movie: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload movie")
    finally:
        # Удаляем временный файл
        if os.path.exists(file_path):
            os.remove(file_path)



from starlette.responses import StreamingResponse

@admin_route.get("/download_movie/{movie_id}", response_class=StreamingResponse)
async def download_movie(
        movie_id: int,
        db: Session = Depends(get_db),
        minio_client: MinioClientWrapper = Depends(get_minio_client)
):
    movie = get_movie_by_id(db, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Фильм не найден")

    try:
        # Получаем поток данных из MinIO
        file_stream = minio_client.download_movie(movie.s3_key)

        # Настраиваем заголовки для скачивания файла
        headers = {
            "Content-Disposition": f'attachment; filename="{movie.title}.mp4"'
        }

        # Возвращаем поток в StreamingResponse
        return StreamingResponse(file_stream, media_type="video/mp4", headers=headers)
    except S3Error as e:
        logger.error(f"Не удалось получить фильм из MinIO: {e}")
        raise HTTPException(status_code=500, detail="Не удалось получить фильм из хранилища")


@admin_route.delete("/delete_movie/{movie_id}")
async def delete_movie_endpoint(
        movie_id: int,
        db: Session = Depends(get_db),
        minio_client: MinioClientWrapper = Depends(get_minio_client)
):
    movie = get_movie_by_id(db, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Фильм не найден")

    try:
        # Удаление файла из MinIO
        minio_client.client.remove_object(minio_client.bucket_name, movie.s3_key)
    except S3Error as e:
        logger.error(f"Не удалось удалить фильм из MinIO: {e}")
        raise HTTPException(status_code=500, detail="Не удалось удалить фильм из хранилища")

    # Удаление записи из базы данных
    success = delete_movie(db, movie_id)
    if not success:
        raise HTTPException(status_code=500, detail="Не удалось удалить фильм из базы данных")

    logger.info(f"Фильм с ID {movie_id} успешно удален.")
    return {"status": "success", "detail": "Фильм успешно удален"}


@admin_route.put("/update_movie/{movie_id}", response_model=MovieResponse)
async def update_movie_endpoint(
        movie_id: int,
        movie_update: MovieUpdate,
        db: Session = Depends(get_db)
):
    updated_movie = update_movie(db, movie_id, title=movie_update.title, description=movie_update.description)
    if not updated_movie:
        raise HTTPException(status_code=404, detail="Фильм не найден или не удалось обновить")

    logger.info(f"Фильм с ID {movie_id} успешно обновлен.")
    return MovieResponse(
        id=updated_movie.id,
        title=updated_movie.title,
        description=updated_movie.description,
        s3_key=updated_movie.s3_key,
        created_at=updated_movie.created_at
    )