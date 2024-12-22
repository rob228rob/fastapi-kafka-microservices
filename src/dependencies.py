# dependencies.py

from fastapi import Request
from src.minio.minio_service import MinioClientWrapper

def get_minio_client(request: Request) -> MinioClientWrapper:
    return request.app.state.minio_client
