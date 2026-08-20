import os
import logging
import pandas as pd
import sqlite3
from datetime import timedelta

logger = logging.getLogger(__name__)

def get_db_files():
    """Get all available database files in the database directory."""
    db_dir = './database'
    if not os.path.exists(db_dir):
        logger.error("数据库目录不存在")
        return []
    return sorted([os.path.join(db_dir, f) for f in os.listdir(db_dir) if f.endswith('.db')])

def get_db_connection(db_file):
    """Create and return a database connection with error handling."""
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error for {db_file}: {e}")
        raise

def load_data_from_multiple_dbs(query, parse_dates=None):
    """Load and combine data from multiple database files."""
    dfs = []
    db_files = get_db_files()
    
    if not db_files:
        logger.error("未找到数据库文件")
        return pd.DataFrame()
    
    for db_file in db_files:
        try:
            with get_db_connection(db_file) as conn:
                df = pd.read_sql_query(query, conn, parse_dates=parse_dates)
                dfs.append(df)
        except Exception as e:
            logger.warning(f"Error loading data from {db_file}: {e}")
            continue
    
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

def load_sales_data():
    """Load sales data from all database files."""
    return load_data_from_multiple_dbs("SELECT * FROM sales", parse_dates=["销售时间"])

def load_loss_data():
    """Load loss data from all database files and process it."""
    df = load_data_from_multiple_dbs("SELECT * FROM loss", parse_dates=["审核时间"])
    if not df.empty:
        df = df.rename(columns={"数量": "报废数量"})
        df["调整日期"] = (df["审核时间"].apply(lambda x: (x - timedelta(hours=5)).date()).ffill())
    return df

def load_card_data():
    """Load card data from all database files."""
    return load_data_from_multiple_dbs("SELECT * FROM cards", parse_dates=["日期"])

def load_financial_data():
    """Load financial data from all database files."""
    return load_data_from_multiple_dbs("SELECT * FROM financial")

def load_weather_data():
    """Load weather data from all database files."""
    return load_data_from_multiple_dbs("SELECT * FROM weather", parse_dates=["日期"])

def load_with_error_handling(load_func, table_name):
    """Load data with error handling."""
    try:
        return load_func()
    except Exception as e:
        logger.error(f"Error loading {table_name} data: {e}")
        return pd.DataFrame()

def load_member_card_data():
    """Load member card data from all database files and parse it."""
    db_files = get_db_files()
    member_data = {
        "member_count": 0,
        "total_amount": 0,
        "principal_amount": 0,
        "gift_amount": 0,
    }
    for db_file in db_files:
        try:
            with get_db_connection(db_file) as conn:
                df = pd.read_sql_query("SELECT * FROM member_card LIMIT 1", conn)
                if not df.empty:
                    member_count = int(df["0"].iloc[0].split("：")[1])
                    total_amount = float(df["1"].iloc[0].split("：")[1].split("（")[0])
                    principal_amount = float(df["1"].iloc[0].split("：")[2].split(" ")[0])
                    gift_amount = total_amount - principal_amount
                    member_data["member_count"] += member_count
                    member_data["total_amount"] += total_amount
                    member_data["principal_amount"] += principal_amount
                    member_data["gift_amount"] += gift_amount
        except Exception as e:
            logger.warning(f"Error loading member card data from {db_file}: {e}")
            continue
    return member_data
