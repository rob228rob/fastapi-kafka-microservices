# src/repositories/movie_repository.py
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .models import BaseDeclaration

logger = logging.getLogger(__name__)


class Movie(BaseDeclaration):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    s3_key = Column(String, unique=True, nullable=False)  # Путь к объекту в S3
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

def create_movie(
        db: Session,
        title: str,
        description: str,
        s3_key: str
) -> Movie:
    new_movie = Movie(title=title, description=description, s3_key=s3_key)
    db.add(new_movie)
    db.commit()
    db.refresh(new_movie)
    return new_movie

def get_movie_by_id(
        db: Session,
        movie_id: int) -> Movie:
    return db.query(Movie).filter(Movie.id == movie_id).first()

def get_movie_by_title(
        db: Session,
        title: str) -> Movie:
    return db.query(Movie).filter(Movie.title == title).first()


def get_all_movies(
        db: Session,
        offset: int = 0,
        limit: int = 100
) -> list:
    if offset < 0 or limit < 0:
        return []

    return db.query(Movie).offset(offset).limit(limit).all()

def delete_movie(
        db: Session,
        movie_id: int
) -> bool:
    try:
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            return False
        db.delete(movie)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при удалении фильма: {e}")
        return False

def update_movie(
        db: Session,
        movie_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None
) -> Optional[Movie]:
    try:
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            return None
        if title is not None:
            movie.title = title
        if description is not None:
            movie.description = description
        db.commit()
        db.refresh(movie)
        return movie
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Ошибка при обновлении фильма: {e}")
        return None