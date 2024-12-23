import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.auth import get_current_active_user, User
from src.producer import send_user_stat_to_kafka
from src.repositories.movie_repository import (
    get_movie_by_id,
    get_all_movies,
)
from src.repositories.user_repository import get_db

# нужно по хорошему вынести в энву и пркоидывать извне, но пока и так сойдет
RECOMMENDATION_SERVICE_URL = "http://localhost:8001/recommendation"

logger = logging.getLogger(__name__)

# Создание роутера
movie_router = APIRouter(
    prefix="/movies",
    tags=["Movies"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

@movie_router.get("/{movie_id}", response_model=dict)
async def get_movie(
        movie_id: int,
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_active_user)
):
    movie = get_movie_by_id(db, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Фильм не найден")

    user_ip = request.client.host
    message = {
        "event": "video_visit",
        "movie_title": movie.title,
        "movie_id": movie_id,
        "user_id": user.id,
        "user_ip": user_ip,
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        send_user_stat_to_kafka(message)
    except Exception as e:
        logger.error(f"Failed to send Kafka message: {e}")

    return {
        "movie_id": movie.id,
        "movie_title": movie.title,
        "movie_description": movie.description,
        "s3_key": movie.s3_key,
        "created_at": movie.created_at,
    }

@movie_router.get("/", response_model=list[dict])
async def get_movies(
    offset: int = Query(0, ge=0, description="Количество записей, которые нужно пропустить"),
    limit: int = Query(10, ge=1, le=100, description="Количество записей, которые нужно вернуть"),
    db: Session = Depends(get_db),
):
    """
    Получить список фильмов с поддержкой пагинации через offset и limit.
    """
    movies = get_all_movies(db, offset, limit)
    return [
        {
            "id": movie.id,
            "title": movie.title,
            "description": movie.description,
            "s3_key": movie.s3_key,
            "created_at": movie.created_at,
        }
        for movie in movies
    ]

@movie_router.get("/recs/{user_id}", response_model=list[dict])
async def get_movie_recommendations(user_id: int):
    try:
        # Выполняем запрос к внешнему сервису
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{RECOMMENDATION_SERVICE_URL}/{user_id}")

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Ошибка сервиса рекомендаций: {response.text}"
            )

        recommendations = response.json()

        return [
            {"movie_id": rec["movie_id"]} for rec in recommendations
        ]
    except httpx.RequestError as e:
        details: str = f"Ошибка подключения к сервису рекомендаций: {str(e)}"
        logging.error(details)
        raise HTTPException(status_code=502, detail=details)
    except Exception as e:
        logging.error(f"Внутренняя ошибка main api: ${str(e)}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка main api: {str(e)}")