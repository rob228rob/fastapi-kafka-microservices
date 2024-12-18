# services/kafka_producer/app/repositories/movie_repository.py

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()

class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    s3_key = Column(String, unique=True, nullable=False)  # Путь к объекту в S3
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

def create_movie(db: Session, title: str, description: str, s3_key: str) -> Movie:
    new_movie = Movie(title=title, description=description, s3_key=s3_key)
    db.add(new_movie)
    db.commit()
    db.refresh(new_movie)
    return new_movie

def get_movie_by_id(db: Session, movie_id: int) -> Movie:
    return db.query(Movie).filter(Movie.id == movie_id).first()

def get_all_movies(db: Session, limit: int = 100) -> list:
    return db.query(Movie).limit(limit).all()