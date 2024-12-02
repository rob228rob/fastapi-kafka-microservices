import json
import os
import psycopg2
import logging
from kafka import KafkaConsumer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler()  # Вывод логов в stdout
    ]
)

logger = logging.getLogger(__name__)

# Чтение переменных окружения
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'mydatabase')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'myuser')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'mypassword')

def initialize_db():
    """
    Создает таблицу messages, если она не существует.
    """
    try:
        conn = psycopg2.connect(
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST
        )
        cursor = conn.cursor()
        # SQL-запрос для создания таблицы, если она не существует
        # для реального кода не подойдет!!!! только для теста
        create_table_query = """
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY,
            timestamp DOUBLE PRECISION,
            message TEXT
        );
        """
        cursor.execute(create_table_query)
        conn.commit()
        logger.info("Таблица 'messages' успешно создана или уже существует.")
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}", exc_info=True)
        raise  # Переброс исключения для остановки приложения, если не удалось инициализировать базу

initialize_db()

# Инициализация Kafka Consumer
consumer = KafkaConsumer(
    'my_topic',
    bootstrap_servers=KAFKA_BROKER,
    value_deserializer=lambda v: json.loads(v.decode('utf-8'))
)

def save_to_db(data):
    try:
        conn = psycopg2.connect(
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST
        )
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (message_id, timestamp, message) VALUES (%s, %s, %s)",
            (data['id'], data['timestamp'], data['message'])
        )
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Сохранено в БД: {data}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении в БД: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Запуск консьюмера...")
    try:
        for message in consumer:
            logger.info(f"Получено сообщение: {message.value}")
            save_to_db(message.value)
    except KeyboardInterrupt:
        logger.info("Консьюмер остановлен пользователем.")
    except Exception as e:
        logger.error(f"Консьюмер столкнулся с ошибкой: {e}", exc_info=True)
