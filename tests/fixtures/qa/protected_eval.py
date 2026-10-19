"""Protected eval fixture (stands in for a frozen test the implementer must never see)."""


def test_login_rejects_wrong_password(client):
    response = client.post("/login", data={"user": "ada", "password": "wrong-horse-battery"})
    assert response.status_code == 401 and response.json()["error"] == "invalid_credentials"
