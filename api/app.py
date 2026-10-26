import csv
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator


PRODUCTS_FILE = Path(__file__).resolve().parent.parent / "products.csv"
PRODUCT_FIELDS = ("product_id", "name", "quantity", "unit")
products_lock = threading.Lock()

app = FastAPI(title="Coffee Supply Inventory API")


class ProductCreate(BaseModel):
    name: str = Field(min_length=1)
    quantity: float = Field(ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1)

    @field_validator("name", "unit")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class StockAdjustment(BaseModel):
    delta: float = Field(allow_inf_nan=False)


def load_products() -> list[dict]:
    if not PRODUCTS_FILE.exists():
        return []

    with PRODUCTS_FILE.open("r", newline="", encoding="utf-8") as products_file:
        reader = csv.DictReader(products_file)
        products = []
        for row in reader:
            try:
                products.append(
                    {
                        "product_id": int(row["product_id"]),
                        "name": row["name"],
                        "quantity": float(row["quantity"]),
                        "unit": row["unit"],
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    return products


def save_products(products: list[dict]) -> None:
    PRODUCTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as products_file:
        writer = csv.DictWriter(products_file, fieldnames=PRODUCT_FIELDS)
        writer.writeheader()
        writer.writerows(products)


@app.get("/inventory")
def get_inventory() -> dict:
    with products_lock:
        products = load_products()
    return {"message": f"Found {len(products)} product(s).", "products": products}


@app.post("/inventory", status_code=201)
def add_product(product: ProductCreate) -> dict:
    with products_lock:
        products = load_products()
        duplicate = next(
            (
                existing
                for existing in products
                if existing["name"].casefold() == product.name.casefold()
                and existing["unit"].casefold() == product.unit.casefold()
            ),
            None,
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"Product '{product.name}' with unit '{product.unit}' already exists.",
            )

        new_product = {
            "product_id": max((item["product_id"] for item in products), default=0) + 1,
            "name": product.name,
            "quantity": product.quantity,
            "unit": product.unit,
        }
        products.append(new_product)
        save_products(products)

    return {"message": f"Added '{product.name}' to inventory.", "product": new_product}


@app.get("/inventory/alerts")
def get_low_stock_alerts(threshold: float = Query(default=10, ge=0)) -> dict:
    with products_lock:
        products = load_products()
    low_stock = [product for product in products if product["quantity"] < threshold]
    return {
        "message": f"Found {len(low_stock)} product(s) below {threshold:g}.",
        "threshold": threshold,
        "products": low_stock,
    }


@app.patch("/inventory/{product_id}")
def adjust_stock(product_id: int, adjustment: StockAdjustment) -> dict:
    with products_lock:
        products = load_products()
        product = next((item for item in products if item["product_id"] == product_id), None)
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")

        updated_quantity = product["quantity"] + adjustment.delta
        if updated_quantity < 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot remove {abs(adjustment.delta):g} {product['unit']} from "
                    f"'{product['name']}'; only {product['quantity']:g} {product['unit']} in stock."
                ),
            )
        product["quantity"] = updated_quantity
        save_products(products)

    return {
        "message": f"Updated '{product['name']}' stock to {updated_quantity:g} {product['unit']}.",
        "product": product,
    }