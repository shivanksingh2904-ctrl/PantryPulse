"""SQLite storage. Returns pandas DataFrames so the UI and engine stay simple."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'Other',
    quantity    REAL NOT NULL,
    unit        TEXT NOT NULL,
    price       REAL NOT NULL DEFAULT 0,
    expiry      TEXT NOT NULL,
    added_on    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',   -- active | used | wasted
    resolved_on TEXT
)"""


class PantryDB:
    def __init__(self, path: str = ":memory:"):
        # Streamlit reruns scripts on different threads, so allow cross-thread use.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def add_item(self, name: str, category: str, quantity: float, unit: str,
                 price: float, expiry: date, today: date | None = None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("Item name is required.")
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")
        if price < 0:
            raise ValueError("Price cannot be negative.")
        cur = self.conn.execute(
            "INSERT INTO items (name, category, quantity, unit, price, expiry, added_on) VALUES (?,?,?,?,?,?,?)",
            (name, category, float(quantity), unit, float(price), expiry.isoformat(),
             (today or date.today()).isoformat()))
        self.conn.commit()
        return int(cur.lastrowid)

    def items(self, status: str | None = None) -> pd.DataFrame:
        sql, params = "SELECT * FROM items", ()
        if status:
            sql, params = sql + " WHERE status = ?", (status,)
        return pd.read_sql_query(sql + " ORDER BY expiry, id", self.conn, params=params)

    def set_status(self, item_id: int, status: str, today: date | None = None) -> None:
        if status not in ("active", "used", "wasted"):
            raise ValueError(f"Invalid status: {status}")
        resolved = None if status == "active" else (today or date.today()).isoformat()
        self.conn.execute("UPDATE items SET status=?, resolved_on=? WHERE id=?", (status, resolved, int(item_id)))
        self.conn.commit()

    def delete(self, item_id: int) -> None:
        self.conn.execute("DELETE FROM items WHERE id=?", (int(item_id),))
        self.conn.commit()

    def clear(self) -> None:
        self.conn.execute("DELETE FROM items")
        self.conn.commit()

    def seed_sample(self, today: date | None = None) -> int:
        """Load demo data (only into an empty database). Returns rows added."""
        if not self.items().empty:
            return 0
        t = today or date.today()
        active = [  # name, category, qty, unit, price, days until expiry
            ("Milk", "Dairy", 1, "L", 60, 1), ("Spinach", "Vegetables", 250, "g", 30, 1),
            ("Tomatoes", "Vegetables", 500, "g", 40, 2), ("Paneer", "Dairy", 200, "g", 90, 3),
            ("Bread", "Bakery", 1, "pack", 45, 0), ("Potatoes", "Vegetables", 1, "kg", 35, 14),
            ("Onions", "Vegetables", 1, "kg", 40, 20), ("Dahi", "Dairy", 400, "g", 40, 4),
            ("Rice", "Grains & Pulses", 5, "kg", 300, 200), ("Dal", "Grains & Pulses", 1, "kg", 140, 150),
            ("Cauliflower", "Vegetables", 1, "pcs", 40, 5), ("Green peas", "Vegetables", 250, "g", 30, -1),
            ("Eggs", "Meat & Eggs", 6, "pcs", 48, 10), ("Capsicum", "Vegetables", 2, "pcs", 25, 6),
            ("Carrots", "Vegetables", 500, "g", 30, 8),
        ]
        for n, c, q, u, p, d in active:
            self.add_item(n, c, q, u, p, t + timedelta(days=d), today=t)
        history = [  # name, category, qty, unit, price, status, days ago resolved
            ("Bananas", "Fruits", 6, "pcs", 40, "wasted", 3), ("Milk", "Dairy", 1, "L", 60, "used", 4),
            ("Spinach", "Vegetables", 250, "g", 30, "used", 6), ("Bread", "Bakery", 1, "pack", 45, "wasted", 9),
            ("Tomatoes", "Vegetables", 500, "g", 40, "used", 10), ("Paneer", "Dairy", 200, "g", 90, "used", 12),
            ("Coriander", "Vegetables", 100, "g", 15, "wasted", 13), ("Eggs", "Meat & Eggs", 12, "pcs", 90, "used", 16),
            ("Cucumber", "Vegetables", 400, "g", 25, "wasted", 18), ("Potatoes", "Vegetables", 1, "kg", 35, "used", 20),
        ]
        for n, c, q, u, p, s, ago in history:
            i = self.add_item(n, c, q, u, p, t - timedelta(days=ago), today=t - timedelta(days=ago + 5))
            self.set_status(i, s, today=t - timedelta(days=ago))
        return len(active) + len(history)
