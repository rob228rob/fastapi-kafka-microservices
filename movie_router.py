from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.auth import get_current_user, get_current_active_user
from src.repositories.movie_repository import (
    get_movie_by_id,
    get_all_movies,
)
from src.repositories.user_repository import get_db

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
        db: Session = Depends(get_db)
):
    """
    Получить информацию о фильме по его ID.
    """
    movie = get_movie_by_id(db, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Фильм не найден")
    return {
        "id": movie.id,
        "title": movie.title,
        "description": movie.description,
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
