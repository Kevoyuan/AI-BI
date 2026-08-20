"""
Fetch sales data through PosPal OpenAPI.

Required environment variables:
- POSPAL_APP_ID
- POSPAL_APP_KEY
- POSPAL_API_BASE_URL, optional
"""

from __future__ import annotations

import argparse
import calendar
import sqlite3
from datetime import datetime

from dotenv import load_dotenv

from modules.pospal_openapi import PospalOpenApiClient, PospalOpenApiConfig, normalize_tickets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--month", type=int, default=datetime.now().month)
    parser.add_argument("--db", default=None, help="SQLite output path")
    parser.add_argument("--page-size", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    load_dotenv(".env")
    args = parse_args()
    _, last_day = calendar.monthrange(args.year, args.month)
    start_time = datetime(args.year, args.month, 1, 0, 0, 0)
    end_time = datetime(args.year, args.month, last_day, 23, 59, 59)
    db_path = args.db or f"database/business_data_{args.year}{args.month:02d}_api.db"

    client = PospalOpenApiClient(PospalOpenApiConfig.from_env())
    tickets = list(client.iter_tickets(start_time, end_time, page_size=args.page_size))
    ticket_df, item_df, payment_df = normalize_tickets(tickets)

    with sqlite3.connect(db_path) as conn:
        ticket_df.to_sql("api_sales_detail", conn, if_exists="replace", index=False)
        item_df.to_sql("api_sales", conn, if_exists="replace", index=False)
        payment_df.to_sql("api_payments", conn, if_exists="replace", index=False)

    print(f"Fetched {len(ticket_df)} tickets, {len(item_df)} items, {len(payment_df)} payments")
    print(f"Wrote {db_path}")


if __name__ == "__main__":
    main()
