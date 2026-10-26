import csv

from fastapi.testclient import TestClient

from api import app as inventory_api


def test_inventory_create_adjust_alerts_and_persistence(tmp_path, monkeypatch):
    products_file = tmp_path / "products.csv"
    monkeypatch.setattr(inventory_api, "PRODUCTS_FILE", products_file)
    client = TestClient(inventory_api.app)

    created = client.post(
        "/inventory", json={"name": "Oat milk", "quantity": 8, "unit": "cartons"}
    )
    assert created.status_code == 201
    product = created.json()["product"]
    assert product == {
        "product_id": 1,
        "name": "Oat milk",
        "quantity": 8,
        "unit": "cartons",
    }

    adjusted = client.patch(f"/inventory/{product['product_id']}", json={"delta": 5})
    assert adjusted.status_code == 200
    assert adjusted.json()["product"]["quantity"] == 13

    alerts = client.get("/inventory/alerts")
    assert alerts.status_code == 200
    assert alerts.json()["products"] == []
    assert client.get("/inventory/alerts?threshold=14").json()["products"] == [
        adjusted.json()["product"]
    ]

    with products_file.open(newline="", encoding="utf-8") as saved_file:
        saved = list(csv.DictReader(saved_file))
    assert saved[0]["quantity"] == "13.0"


def test_inventory_validation_and_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(inventory_api, "PRODUCTS_FILE", tmp_path / "products.csv")
    client = TestClient(inventory_api.app)

    assert client.post(
        "/inventory", json={"name": " ", "quantity": 2, "unit": "kg"}
    ).status_code == 422
    assert client.post(
        "/inventory", json={"name": "Beans", "quantity": 2, "unit": "kg"}
    ).status_code == 201
    assert client.post(
        "/inventory", json={"name": "beans", "quantity": 1, "unit": "KG"}
    ).status_code == 409
    assert client.patch("/inventory/1", json={"delta": -3}).status_code == 409
    assert client.patch("/inventory/99", json={"delta": 1}).status_code == 404
    assert client.get("/inventory/alerts?threshold=-1").status_code == 422