# minio_service.py

import logging

from fastapi import HTTPException, status
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

class MinioClientWrapper:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False, bucket_name: str = "movies"):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.bucket_name = bucket_name
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Bucket '{self.bucket_name}' создан.")
            else:
                logger.info(f"Bucket '{self.bucket_name}' уже существует.")
        except S3Error as e:
            logger.error(f"Ошибка при проверке/создании бакета: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось инициализировать хранилище."
            )

    def upload_movie(self, object_name: str, file_path: str):
        """
        Загружает файл (фильм) в bucket MinIO
        :param object_name: имя объекта (файла) в хранилище
        :param file_path: локальный путь к файлу
        """
        try:
            self.client.fput_object(self.bucket_name, object_name, file_path)
            logger.info(f"Файл {object_name} успешно загружен в {self.bucket_name}.")
        except S3Error as err:
            logger.error(f"Ошибка при загрузке файла: {err}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось загрузить файл в хранилище."
            )

    def download_movie(self, object_name: str):
        """
        Скачивает файл (фильм) из bucket MinIO и возвращает поток
        :param object_name: имя объекта (файла) в хранилище
        :return: поток данных файла
        """
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            logger.info(f"Файл {object_name} успешно получен из {self.bucket_name}.")
            return response  # Возвращаем поток
        except S3Error as err:
            logger.error(f"Ошибка при скачивании файла: {err}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось скачать файл из хранилища."
            )
