# tests/test_api.py
import pytest
from unittest.mock import patch
from src.repositories.user_repository import create_user, assign_role_to_user, get_user_by_username
from ..auth import get_password_hash

@pytest.mark.usefixtures("test_db")
def test_register_user(client):
    response = client.post("/register", json={"username": "newuser", "password": "secret", "full_name": "New User", "roles": ["admin"]})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "token_type" in data

    # Проверим, что пользователь реально в БД
    user = get_user_by_username("newuser")
    assert user is not None
    assert user["full_name"] == "New User"
    roles = user["roles"]
    assert "admin" in roles

@pytest.mark.usefixtures("test_db")
def test_login_user(client):
    # Создадим пользователя напрямую в БД
    user_id = create_user("loginuser", get_password_hash("secret"))
    assign_role_to_user(user_id, "user")
    response = client.post("/login", data={"username": "loginuser", "password": "secret"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

@pytest.mark.usefixtures("test_db")
def test_protected_route_without_token(client):
    response = client.get("/protected/")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers

@pytest.mark.usefixtures("test_db")
def test_protected_route_with_token(client):
    # Создадим пользователя и получим токен
    user_id = create_user("protuser", get_password_hash("secret"))
    response = client.post("/login", data={"username": "protuser", "password": "secret"})
    token = response.json()["access_token"]

    response = client.get("/protected/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "Hello, protuser!" in response.json()["message"]

@pytest.mark.usefixtures("test_db")
def test_admin_endpoint_forbidden(client):
    # Создадим пользователя без admin роли
    user_id = create_user("normaluser", get_password_hash("secret"))
    assign_role_to_user(user_id, "user")
    response = client.post("/login", data={"username": "normaluser", "password": "secret"})
    token = response.json()["access_token"]

    # Попытка зайти на /admin/users
    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

@pytest.mark.usefixtures("test_db")
def test_admin_endpoint_allowed(client):
    # Создадим пользователя c admin ролью
    user_id = create_user("adminuser", get_password_hash("secret"))
    assign_role_to_user(user_id, "admin")
    response = client.post("/login", data={"username": "adminuser", "password": "secret"})
    token = response.json()["access_token"]

    # Доступ к /admin/users
    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "Вы имеете доступ как администратор" in response.json()["message"]

@pytest.mark.usefixtures("test_db")
def test_send_kafka_message(client):
    # Создадим пользователя c ролью user (допустим доступен)
    user_id = create_user("kafkau", get_password_hash("secret"))
    assign_role_to_user(user_id, "user")
    response = client.post("/login", data={"username": "kafkau", "password": "secret"})
    token = response.json()["access_token"]

    test_message = {"key": "value"}

    with patch("src.producer.send_message") as mock_send:
        mock_send.return_value = None
        response = client.post("/send/", json=test_message, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_send.assert_called_once_with(test_message)
