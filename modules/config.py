"""
Application Configuration
Centralised config dataclass + domain-level constants.
"""
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class Config:
    """Application-wide settings."""

    # LLM Provider
    LLM_PROVIDER: str = "deepseek"          # "deepseek" | "gemini"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    GEMINI_MODEL: str = "gemini-1.5-flash"
    MODEL_NAME: str = "deepseek-chat"

    # Inference limits
    MAX_TOKENS: int = 8192
    MAX_RETRIES: int = 3
    TIMEOUT: int = 30

    # Data limits
    CACHE_SIZE: int = 128
    MAX_DATA_ROWS: int = 10_000
    CHART_HEIGHT: int = 500

    # Paths
    DATA_DIR: str = "./database"


@dataclass
class TableConfig:
    """Schema metadata for a single database table."""
    time_field: Optional[str]
    amount_field: Optional[str]
    category_field: Optional[str]
    description: str


# ── Table registry ────────────────────────────────────────────────────────────
# Field names are generic English keys; map them to your actual column names
# inside each loader function.
TABLE_CONFIGS: Dict[str, TableConfig] = {
    "sales":        TableConfig("sale_time",    "amount",       "category",  "Sales transaction line-items"),
    "sales_detail": TableConfig("sale_date",    "amount",       None,        "Order-level daily receipts"),
    "waste":        TableConfig("audit_time",   "waste_amount", "category",  "Waste / shrinkage records"),
    "memberships":  TableConfig("date",         "recharge_amt", None,        "Membership card daily summary"),
    "mem_detail":   TableConfig("recharge_time","recharge_amt", None,        "Membership card recharge log"),
    "financial":    TableConfig(None,           "amount",       "type",      "Fixed cost parameters"),
    "weather":      TableConfig("date",         None,           "condition", "Daily weather log"),
    "opening_cost": TableConfig(None,           "amount",       "type",      "Store opening cost items"),
}

# ── COGS ratios by product category ──────────────────────────────────────────
CATEGORY_COST_RATIOS: Dict[str, float] = {
    "fresh_baked":    0.35,
    "pastry":         0.40,
    "handcraft":      0.35,
    "beverages":      0.90,
    "birthday_cake":  0.40,
    "sharing_cake":   0.40,
    "other":          0.35,
    "default":        0.40,
}

# ── Pre-built question templates for the AI Q&A page ─────────────────────────
QUESTION_TEMPLATES: Dict[str, list] = {
    "📊 Sales Analysis": [
        "What is the sales trend for the last 7 days?",
        "Which product category performs best?",
        "How does today compare to yesterday?",
        "What are the top 10 best-selling items?",
        "How does weekend revenue compare to weekdays?",
    ],
    "📉 Waste Analysis": [
        "How severe is the current waste situation?",
        "Which category has the most waste?",
        "Is the waste rate within acceptable range?",
        "Show daily waste amount trend.",
        "How can we reduce the waste rate?",
    ],
    "💳 Membership Analysis": [
        "How is membership card recharge trending?",
        "What is the membership consumption rate?",
        "Show membership recharge amount distribution.",
        "What percentage of sales come from members?",
    ],
    "🌤️ Weather Impact": [
        "How does weather affect sales?",
        "Compare sunny vs rainy day revenue.",
        "Which product categories are most weather-sensitive?",
    ],
    "💰 Profit Analysis": [
        "What is the net profit margin trend?",
        "Show cost breakdown.",
        "Which time slot is most profitable?",
        "Suggest ways to improve profit margin.",
    ],
    "⏰ Time-Slot Analysis": [
        "Which hour of the day has the most orders?",
        "Show morning / lunch / afternoon / evening distribution.",
        "Suggest staffing schedule based on peak hours.",
    ],
    "📈 Forecasting": [
        "Forecast sales for the next 7 days.",
        "Identify seasonal sales patterns.",
        "What is the estimated revenue for next month?",
    ],
    "🔍 Deep Insights": [
        "Give a comprehensive performance assessment.",
        "What are the key growth opportunities?",
        "Identify the main operational bottlenecks.",
    ],
}

# ── Business metric definitions (used to build AI context) ───────────────────
BUSINESS_LOGIC_DEFINITIONS: Dict[str, dict] = {
    "revenue": {
        "source_table": "sales_detail",
        "calculation": "sum('amount')",
        "description": "Total revenue: order-level 'amount' sum, avoiding double-counting from line-item splits.",
    },
    "net_profit": {
        "formula": "revenue - COGS - operating_cost - fixed_cost",
        "description": "Net profit after all cost deductions.",
    },
    "net_profit_margin": {
        "formula": "net_profit / revenue",
        "description": "Net profit margin: key profitability KPI.",
    },
    "transaction_count": {
        "source_table": "sales",
        "calculation": "nunique('order_id')",
        "description": "TC (Transaction Count): unique orders, de-duplicated by order_id.",
    },
    "average_check": {
        "formula": "revenue / transaction_count",
        "description": "AC (Average Check): average spend per order.",
    },
    "waste": {
        "source_table": "waste",
        "description": "Waste amount excluding product samples and non-operational write-offs.",
    },
    "target_achievement": {
        "calculation": "actual / target",
        "description": "Target achievement rate, compared against day-of-week targets.",
    },
}

# ── Data dictionary (helps AI understand all fields) ─────────────────────────
DATA_DICTIONARY: Dict[str, dict] = {
    "sales": {
        "sale_time":  "Timestamp of the sale",
        "product":    "Product name",
        "category":   "Product category",
        "amount":     "Actual received amount",
        "list_price": "Listed price",
        "qty":        "Quantity sold",
        "order_id":   "Order ID used to compute TC (transaction count)",
    },
    "sales_detail": {
        "sale_date":    "Sale date",
        "amount":       "Order-level amount received",
        "digital_pay":  "Mobile / digital payment amount",
        "card_pay":     "Membership card payment",
        "cash":         "Cash payment",
        "platform_pay": "Third-party platform payment",
    },
    "waste": {
        "audit_time":   "Waste audit timestamp",
        "adj_date":     "Adjusted date (audit_time − 5 h shift)",
        "product":      "Wasted product name",
        "category":     "Wasted product category",
        "waste_amount": "Waste amount (monetary)",
        "qty":          "Wasted quantity",
        "note":         "Note: distinguishes samples / normal waste",
        "reason":       "Waste reason",
    },
    "memberships": {
        "date":          "Date",
        "recharge_amt":  "Total recharge amount",
        "consumed_amt":  "Total consumption from membership card",
        "principal_amt": "Principal portion consumed",
        "gift_amt":      "Gift/bonus portion consumed",
    },
    "daily_summary": {
        "date":          "Date",
        "amount":        "Daily revenue",
        "list_total":    "Daily total list price",
        "orders":        "Daily order count (TC)",
        "net_profit":    "Daily net profit",
        "profit_margin": "Daily net profit margin",
        "cogs":          "Cost of goods sold",
        "op_cost":       "Operating expense",
        "fixed_cost":    "Fixed daily cost",
        "waste_total":   "Total waste",
        "samples":       "Sample / tasting cost",
        "waste_fresh":   "Fresh-baked waste",
        "waste_pastry":  "Pastry waste",
    },
}

config = Config()
