# streaming.py

import logging
from datetime import datetime
from typing import Generator

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from minio import S3Error
from sqlalchemy.orm import Session

from ..auth import get_current_active_user, User
from ..dependencies import get_minio_client
from ..minio.minio_service import MinioClientWrapper
from ..producer import send_user_stat_to_kafka
from ..repositories.movie_repository import get_movie_by_title, get_movie_by_id
from ..repositories.user_repository import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/streaming",
    tags=["Streaming"],  # Теги для группировки в документации
    dependencies=[Depends(get_current_active_user)],  # Все маршруты требуют аутентифицированного пользователя
    responses={404: {"description": "Not found"}},
)


def get_minio_client_dependency(request: Request) -> MinioClientWrapper:
    return request.app.state.minio_client


@router.get("/get/{movie_id}", response_class=StreamingResponse, responses={
    200: {"content": {"video/mp4": {}}},
    404: {"description": "Video not found"},
})
async def download_movie(
        movie_id: int,
        request: Request,
        db: Session = Depends(get_db),
        requested_user: User = Depends(get_current_active_user),
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

        user_ip = request.client.host
        message = {
            "event": "video_streamed",
            "movie_title": movie.title,
            "movie_id": movie_id,
            "user_id": requested_user.id,
            "user_ip": user_ip,
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            send_user_stat_to_kafka(message)
        except Exception as e:
            logger.error(f"Failed to send Kafka message: {e}")

        return StreamingResponse(file_stream, media_type="video/mp4", headers=headers)
    except S3Error as e:
        logger.error(f"Не удалось получить фильм из MinIO: {e}")
        raise HTTPException(status_code=500, detail="Не удалось получить фильм из хранилища")