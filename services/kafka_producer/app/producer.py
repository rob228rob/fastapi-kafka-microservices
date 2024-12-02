# app/kafka_producer.py

from kafka import KafkaProducer
import json
import os
import logging

logger = logging.getLogger(__name__)

KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')

# Инициализация Kafka Producer с Гарантией At Least Once и идемпотентностью
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    acks='all',  # Ожидание подтверждения от всех реплик
    retries=3,  # Количество повторных попыток
    max_in_flight_requests_per_connection=5,  # Максимальное количество не подтвержденных запросов
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)


def send_message(message: dict, topic: str = 'my_topic'):
    """
    Отправка сообщения в Kafka
    """
    future = producer.send(topic, value=message)
    try:
        record_metadata = future.get(timeout=5)
        logger.info(f"Message sent to {record_metadata.topic} partition {record_metadata.partition} offset {record_metadata.offset}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        raise e
