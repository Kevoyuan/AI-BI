"""
Mock Data Generator
Generates realistic demo SQLite databases for local development and testing.
Run this script once to populate the database/ directory with sample data.

Usage:
    python data/mock/generate_mock_data.py

Output:
    database/sales_data_YYYYMM.db  (last 3 months)
"""
import os
import sqlite3
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "database")
os.makedirs(DB_DIR, exist_ok=True)

# ── Demo product catalogue ─────────────────────────────────────────────────────
PRODUCTS = [
    ("Croissant",         "fresh_baked",  4.5,  0.35),
    ("Pain au chocolat",  "fresh_baked",  5.0,  0.35),
    ("Sourdough loaf",    "fresh_baked",  9.0,  0.35),
    ("Cinnamon roll",     "pastry",       4.0,  0.40),
    ("Cheese danish",     "pastry",       4.5,  0.40),
    ("Almond croissant",  "pastry",       5.5,  0.40),
    ("Birthday cake 6\"", "birthday_cake",38.0, 0.40),
    ("Sharing cake 8\"",  "sharing_cake", 48.0, 0.40),
    ("Shortbread pack",   "handcraft",    6.5,  0.35),
    ("Brownie",           "handcraft",    3.5,  0.35),
    ("Latte",             "beverages",    5.0,  0.90),
    ("Cappuccino",        "beverages",    4.8,  0.90),
    ("Matcha latte",      "beverages",    5.5,  0.90),
    ("Orange juice",      "beverages",    4.0,  0.90),
]

PAYMENT_TYPES = ["digital_pay", "cash", "card_pay", "platform_pay"]

WEATHER_CONDITIONS = ["sunny", "cloudy", "overcast", "light_rain", "moderate_rain"]
WEATHER_WEIGHTS    = [0.40,    0.25,    0.15,        0.12,          0.08]
WEATHER_MULTIPLIER = {"sunny": 1.00, "cloudy": 0.95, "overcast": 0.90,
                      "light_rain": 0.80, "moderate_rain": 0.65}


def _simulate_day(day: date, weather: str) -> tuple[list, list]:
    """Return (sales_rows, waste_rows) for one day."""
    weekday = day.weekday()

    # Base order count by day type
    if weekday <= 3:
        base_orders = random.randint(150, 250)
    elif weekday == 4:
        base_orders = random.randint(200, 300)
    elif weekday == 5:
        base_orders = random.randint(300, 450)
    else:
        base_orders = random.randint(350, 500)

    base_orders = int(base_orders * WEATHER_MULTIPLIER[weather])

    # Sales
    sales = []
    for order_num in range(base_orders):
        order_id  = f"{day.strftime('%Y%m%d')}-{order_num:04d}"
        n_items   = max(1, int(np.random.poisson(2.5)))
        hour      = _pick_hour()
        minute    = random.randint(0, 59)
        ts        = f"{day} {hour:02d}:{minute:02d}:00"

        order_total = 0.0
        for _ in range(n_items):
            product, category, price, _ = random.choice(PRODUCTS)
            qty = 1
            disc = random.choice([0, 0, 0, 0.1, 0.2])
            actual = round(price * (1 - disc), 2)
            order_total += actual
            sales.append({
                "sale_time":   ts,
                "product":     product,
                "category":    category,
                "list_price":  price,
                "amount":      actual,
                "qty":         qty,
                "order_id":    order_id,
            })

        # Payment split
        pay_type = random.choices(PAYMENT_TYPES, weights=[0.65, 0.10, 0.20, 0.05])[0]
        sales[-n_items:] = [
            {**r, "payment_type": pay_type} for r in sales[-n_items:]
        ]

    # Waste
    waste = []
    n_waste = random.randint(3, 12)
    for _ in range(n_waste):
        product, category, price, _ = random.choice(
            [p for p in PRODUCTS if p[1] in ("fresh_baked", "pastry", "handcraft")]
        )
        qty    = random.randint(1, 5)
        reason = random.choice(["end_of_day", "damaged", "sample", "quality_issue"])
        note   = f"{category} - {reason}"
        audit_hour = random.randint(18, 23)
        adj_ts     = f"{day} {audit_hour}:00:00"
        adj_date   = day

        waste.append({
            "audit_time":   adj_ts,
            "adj_date":     str(adj_date),
            "product":      product,
            "category":     category,
            "waste_amount": round(price * qty * 0.8, 2),
            "qty":          qty,
            "note":         note,
            "reason":       reason,
        })

    return sales, waste


def _pick_hour() -> int:
    """Return a realistic operating hour weighted by typical foot traffic."""
    hours   = list(range(7, 22))
    weights = [2, 5, 8, 10, 8, 6, 10, 12, 10, 8, 6, 5, 4, 3, 2]
    return random.choices(hours, weights=weights)[0]


def generate_month(year: int, month: int) -> None:
    """Generate and write one month of demo data to a SQLite database."""
    month_str = f"{year}{month:02d}"
    db_path   = os.path.join(DB_DIR, f"sales_data_{month_str}.db")

    all_sales, all_waste = [], []

    start = date(year, month, 1)
    end   = (date(year, month + 1, 1) - timedelta(days=1)) if month < 12 else date(year, 12, 31)

    weather_log = []
    day = start
    while day <= end:
        cond = random.choices(WEATHER_CONDITIONS, weights=WEATHER_WEIGHTS)[0]
        weather_log.append({"date": str(day), "condition": cond})

        sales, waste = _simulate_day(day, cond)
        all_sales.extend(sales)
        all_waste.extend(waste)
        day += timedelta(days=1)

    df_sales   = pd.DataFrame(all_sales)
    df_waste   = pd.DataFrame(all_waste)
    df_weather = pd.DataFrame(weather_log)

    # Membership recharge (aggregated daily)
    mem_rows = []
    for entry in weather_log:
        n = random.randint(2, 15)
        mem_rows.append({
            "date":          entry["date"],
            "recharge_amt":  round(n * random.uniform(30, 80), 2),
            "consumed_amt":  round(n * random.uniform(20, 60), 2),
            "principal_amt": round(n * random.uniform(15, 50), 2),
            "gift_amt":      round(n * random.uniform(5, 20), 2),
        })
    df_memberships = pd.DataFrame(mem_rows)

    with sqlite3.connect(db_path) as conn:
        df_sales.to_sql("sales",       conn, if_exists="replace", index=False)
        df_waste.to_sql("waste",       conn, if_exists="replace", index=False)
        df_weather.to_sql("weather",   conn, if_exists="replace", index=False)
        df_memberships.to_sql("memberships", conn, if_exists="replace", index=False)

    print(f"✅ Generated {db_path} — {len(df_sales)} sales rows, {len(df_waste)} waste rows")


def generate_static_files() -> None:
    """Generate CSV helper files: financial params, member summary."""
    # Financial parameters
    fp = pd.DataFrame([{"fixed_cost": 1500.0, "cogs_ratio": 0.35, "op_cost_ratio": 0.12}])
    fp.to_csv(os.path.join(DB_DIR, "financial_params.csv"), index=False)

    # Member summary (all-time totals)
    ms = pd.DataFrame([{
        "member_count": random.randint(500, 2000),
        "total_balance": random.uniform(50000, 200000),
        "principal":     random.uniform(40000, 160000),
        "gift_balance":  random.uniform(5000, 40000),
    }])
    ms.to_csv(os.path.join(DB_DIR, "member_summary.csv"), index=False)

    print("✅ Generated financial_params.csv and member_summary.csv")


if __name__ == "__main__":
    import sys
    from datetime import date as _date

    today = _date.today()

    # Generate last 3 months
    for delta in [2, 1, 0]:
        m = today.month - delta
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        generate_month(y, m)

    generate_static_files()
    print("\n🎉 Mock data generation complete!")
    print(f"   Database files: {DB_DIR}")
