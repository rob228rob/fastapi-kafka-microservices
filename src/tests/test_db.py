# tests/test_db.py
import pytest
from src.repositories.user_repository import create_user, get_user_by_id, get_user_by_username, assign_role_to_user, get_user_roles

@pytest.mark.usefixtures("test_db")
def test_create_user():
    user_id = create_user("testuser", "hashed_pass", "Test User")
    user = get_user_by_id(user_id)
    assert user is not None
    assert user["username"] == "testuser"
    assert user["full_name"] == "Test User"
    assert user["hashed_password"] == "hashed_pass"

@pytest.mark.usefixtures("test_db")
def test_get_user_by_username():
    user_id = create_user("testuser2", "hashed_pass2", "Another User")
    user = get_user_by_username("testuser2")
    assert user is not None
    assert user["id"] == user_id

@pytest.mark.usefixtures("test_db")
def test_assign_role_to_user():
    user_id = create_user("testuser3", "hashed_pass3")
    assign_role_to_user(user_id, "admin")
    roles = get_user_roles(user_id)
    assert "admin" in roles

@pytest.mark.usefixtures("test_db")
def test_get_user_roles():
    user_id = create_user("testuser4", "hashed_pass4")
    assign_role_to_user(user_id, "user")
    assign_role_to_user(user_id, "editor")
    roles = get_user_roles(user_id)
    assert "user" in roles
    assert "editor" in roles
