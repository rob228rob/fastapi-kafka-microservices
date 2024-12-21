# streaming.py

import os
from typing import Generator
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_active_user, User
from app.producer import send_message
from app.repositories.movie_repository import get_movie_by_title, create_movie
from app.repositories.user_repository import get_all_users, get_db
from pydantic_models import UserOut, UsersResponse
from app.minio.minio_service import MinioClientWrapper

import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/streaming",  # Все маршруты будут начинаться с /streaming
    tags=["Streaming"],  # Теги для группировки в документации
    dependencies=[Depends(get_current_active_user)],  # Все маршруты требуют аутентифицированного пользователя
    responses={404: {"description": "Not found"}},
)


# Генерация чанков для стриминга
def file_chunk_generator(file_obj, chunk_size: int = 512 * 512) -> Generator[bytes, None, None]:
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        yield chunk


def get_minio_client_dependency(request: Request) -> MinioClientWrapper:
    return request.app.state.minio_client


@router.get("/get/{video_title}", response_class=StreamingResponse, responses={
    200: {"content": {"video/mp4": {}}},
    404: {"description": "Video not found"},
})
async def get_video(
        video_title: str,
        request: Request,
        db: Session = Depends(get_db),
        minio_client: MinioClientWrapper = Depends(get_minio_client_dependency),
        current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    # Получение метаданных фильма из базы данных
    movie = get_movie_by_title(db, title=video_title)
    if not movie:
        raise HTTPException(status_code=404, detail="Video not found")

    # Получение объекта из MinIO
    try:
        response = minio_client.client.get_object(movie.s3_key)
    except Exception as e:
        logger.error(f"Failed to retrieve video from MinIO: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve video")

    user_ip = request.client.host
    message = {
        "event": "video_streamed",
        "video_title": video_title,
        "user": current_user.username,
        "user_ip": user_ip,
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        send_message(message)
    except Exception as e:
        logger.error(f"Failed to send Kafka message: {e}")

    return StreamingResponse(file_chunk_generator(response), media_type="video/mp4")


@router.get("/play/plyr/{video_title}", response_class=HTMLResponse)
async def play_video_plyr(
        video_title: str,
        request: Request,
        db: Session = Depends(get_db),
        minio_client: MinioClientWrapper = Depends(get_minio_client_dependency),
        current_user: User = Depends(get_current_active_user)
) -> HTMLResponse:
    # Проверка существования фильма в базе данных
    movie = get_movie_by_title(db, title=video_title)
    if not movie:
        raise HTTPException(status_code=404, detail="Video not found")

    return HTMLResponse(
        content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <link href="https://cdn.plyr.io/3.6.8/plyr.css" rel="stylesheet" />
        </head>
        <body>
            <video id="player" playsinline controls>
                <source src="/streaming/get/{video_title}" type="video/mp4" />
            </video>
            <script src="https://cdn.plyr.io/3.6.8/plyr.polyfilled.js"></script>
            <script>
                const player = new Plyr('#player');
            </script>
        </body>
        </html>
        """,
        status_code=200
    )