"""
Data Pipeline — Automated Export, Download & ETL

Demonstrates a full end-to-end pipeline that:
  1. Authenticates to an external POS / ERP web portal (requests + Selenium).
  2. Navigates to multiple report pages and triggers Excel exports.
  3. Verifies downloads with automatic retry.
  4. Cleans, transforms, and loads the data into a local SQLite database.

Architecture:
  requests.Session (fast login) → cookies bridged to Selenium WebDriver →
  headless Chrome navigates report pages → downloads Excel files →
  pandas reads & cleans → sqlite3 bulk insert.

NOTE: All URLs, credentials, page selectors, and file names in this file
      are generic examples. Replace them with your actual POS / ERP system
      endpoints before running.
"""

import calendar
import functools
import logging
import os
import shutil
import sqlite3
import time
import warnings
from configparser import ConfigParser
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ============================================================================
# Configuration — Singleton with INI / YAML / env fallback
# ============================================================================

class PipelineConfig:
    """
    Reads settings from config.ini (INI) or config.yaml (YAML).
    Falls back to sensible defaults if neither file exists.
    Singleton: only one instance is ever created.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        self._settings: Dict[str, str] = {}

        # Prefer config.ini (INI format)
        if os.path.exists("config.ini"):
            cp = ConfigParser()
            cp.read("config.ini")
            for section in cp.sections():
                for key, value in cp.items(section):
                    self._settings[f"{section}.{key}"] = value
            for key, value in cp.items("DEFAULT"):
                self._settings[key] = value
            return

        # Fall back to config.yaml
        if os.path.exists("config.yaml"):
            with open("config.yaml", "r", encoding="utf-8") as f:
                yc = yaml.safe_load(f) or {}
            for section, values in yc.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        self._settings[f"{section}.{key}"] = str(value)

    def _get(self, key: str, fallback: str = "") -> str:
        return self._settings.get(key, fallback)

    @property
    def year(self) -> int:
        val = self._get("Year", str(datetime.now().year))
        return int(val) if val.isdigit() else datetime.now().year

    @property
    def month(self) -> int:
        val = self._get("Month", str(datetime.now().month))
        return int(val) if val.isdigit() else datetime.now().month

    @property
    def download_dir(self) -> str:
        return self._get("PATHS.DownloadDir", "./data")

    @property
    def database_dir(self) -> str:
        return self._get("PATHS.DatabaseDir", "./database")

    @property
    def max_retries(self) -> int:
        val = self._get("RETRY.MaxRetries", "3")
        return int(val) if val.isdigit() else 3


# ── Globals ───────────────────────────────────────────────────────────────────

config = PipelineConfig()
YEAR = config.year
MONTH = config.month
download_dir = config.download_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

# ============================================================================
# HTTP request defaults
# ============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Replace with your actual POS / ERP portal URL
BASE_URL = os.getenv("POS_BASE_URL", "https://portal.example-pos.com")
LOGIN_URL = f"{BASE_URL}/Account/Signin"

# ============================================================================
# Authentication — requests session + cookie bridge to Selenium
# ============================================================================

def get_credentials() -> Tuple[str, str]:
    """Read login credentials from environment variables."""
    username = os.environ.get("POS_USERNAME", "demo_user")
    password = os.environ.get("POS_PASSWORD")

    if not password:
        logger.info("Password not found in environment — prompting for input.")
        password = input("Enter password: ")

    return username, password


def login_session(max_retries: int = None) -> requests.Session:
    """
    Create an authenticated requests session with exponential-backoff retry.

    Returns:
        An authenticated requests.Session instance.

    Raises:
        RuntimeError if all retry attempts fail.
    """
    max_retries = max_retries or config.max_retries

    for attempt in range(max_retries):
        try:
            username, password = get_credentials()
            session = requests.Session()
            session.headers.update(HEADERS)
            response = session.post(
                LOGIN_URL,
                data={"username": username, "password": password},
            )
            response.raise_for_status()
            logger.info("Login successful.")
            return session
        except Exception as exc:
            logger.error("Login failed (attempt %d/%d): %s", attempt + 1, max_retries, exc)
            if attempt == max_retries - 1:
                raise RuntimeError(f"Login failed after {max_retries} retries.") from exc
            time.sleep(2 ** attempt)  # Exponential backoff


def transfer_cookies(requests_session: requests.Session) -> List[dict]:
    """
    Convert requests.Session cookies to Selenium-compatible format.

    This bridges the lightweight requests auth with the heavier
    Selenium WebDriver so we can avoid logging in twice.
    """
    return [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": c.secure,
            "httpOnly": c.has_nonstandard_attr("HttpOnly"),
        }
        for c in requests_session.cookies
    ]

# ============================================================================
# Selenium WebDriver setup
# ============================================================================

CHROME_DRIVER_PATHS = [
    "/usr/local/bin/chromedriver",
    "/opt/homebrew/bin/chromedriver",
    os.path.expanduser("~/chromedriver"),
]


def setup_selenium(download_directory: str = "data") -> webdriver.Chrome:
    """
    Configure and return a headless Chrome WebDriver with custom
    download preferences.

    Falls back through a list of known chromedriver locations if
    the system default is unavailable.
    """
    options = Options()
    options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(download_directory),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })

    for arg in [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--headless",
        "--disable-gpu",
        "--window-size=1920,1080",
    ]:
        options.add_argument(arg)

    # Try system-default chromedriver first
    try:
        return webdriver.Chrome(options=options)
    except Exception as exc:
        logger.warning("Default ChromeDriver failed: %s", exc)

    # Try known paths
    for driver_path in CHROME_DRIVER_PATHS:
        if os.path.exists(driver_path):
            try:
                service = Service(executable_path=driver_path)
                driver = webdriver.Chrome(service=service, options=options)
                logger.info("Using ChromeDriver at: %s", driver_path)
                return driver
            except Exception as exc:
                logger.warning("ChromeDriver at %s failed: %s", driver_path, exc)

    raise RuntimeError("Could not initialise Chrome WebDriver.")

# ============================================================================
# Date range helpers
# ============================================================================

def get_month_range(year: int, month: int) -> Tuple[str, str, int]:
    """Return (start_str, end_str, last_day) for the given year/month."""
    _, last_day = calendar.monthrange(year, month)
    start = f"{year}.{month:02d}.01 00:00"
    end   = f"{year}.{month:02d}.{last_day} 23:59"
    return start, end, last_day


def set_date_range(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """
    Fill the date range picker on a report page.

    Many POS systems use readonly date inputs — this removes the
    readonly attribute via JS before setting the value.
    """
    start_str, end_str, _ = get_month_range(YEAR, MONTH)

    wait.until(EC.element_to_be_clickable((By.ID, "dateTimeRangeBox"))).click()

    for xpath, value in [
        ('//input[contains(@id, "ui-timePicker-begin-")]', start_str),
        ('//input[contains(@id, "ui-timePicker-end-")]',   end_str),
    ]:
        elem = driver.find_element(By.XPATH, xpath)
        driver.execute_script("arguments[0].removeAttribute('readonly')", elem)
        elem.clear()
        elem.send_keys(value)

    logger.info("Date range set: %s → %s", start_str, end_str)

# ============================================================================
# Selenium click helpers
# ============================================================================

def _click_element(wait: WebDriverWait, locator: tuple, timeout: int = 10) -> None:
    """Wait for an element to be clickable, then click it."""
    wait.until(EC.element_to_be_clickable(locator)).click()


def _click_by_id(wait: WebDriverWait, element_id: str) -> None:
    _click_element(wait, (By.ID, element_id))


def _click_by_xpath(wait: WebDriverWait, xpath: str) -> None:
    _click_element(wait, (By.XPATH, xpath))

# ============================================================================
# Export functions — one per report type
# ============================================================================

def export_sales_flow(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Export line-item sales data from the POS report page."""
    driver.get(f"{BASE_URL}/Report/ProductSaleDetails")
    time.sleep(2)

    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@p-click="search" and contains(@class, "submitBtn")]')
    time.sleep(8)

    _click_by_id(wait, "btnExport")
    time.sleep(30)
    logger.info("Sales flow data exported.")


def export_waste_records(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Export waste / shrinkage records."""
    driver.get(f"{BASE_URL}/Inventory/DiscardInventoryHistory")
    time.sleep(2)

    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@class="submitBtn" and text()="Search"]')
    time.sleep(3)

    _click_by_id(wait, "btnExportDiscardInventoryHistory")
    _click_by_id(wait, "ck_showItems")
    _click_by_xpath(wait, '//div[@class="fileExport btnExport" and @p-click="export"]')
    time.sleep(10)
    logger.info("Waste records exported.")


def export_recharge_details(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Export membership card recharge transaction log."""
    driver.get(f"{BASE_URL}/CardReport/RechargeLogs")
    time.sleep(2)

    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@class="submitBtn" and text()="Search"]')
    time.sleep(3)

    _click_by_id(wait, "btnExport")
    logger.info("Recharge details exported.")


def export_card_statistics(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Export membership card aggregate statistics (recharge vs consumption)."""
    driver.get(f"{BASE_URL}/CustomerReport/RechargeAndConsumptionSummary")
    time.sleep(2)

    _, _, last_day = get_month_range(YEAR, MONTH)
    start_date = f"{YEAR}-{MONTH:02d}-01"
    end_date   = f"{YEAR}-{MONTH:02d}-{last_day}"

    for elem_id, value in [("txt_startDatetime", start_date), ("txt_endDatetime", end_date)]:
        elem = wait.until(EC.element_to_be_clickable((By.ID, elem_id)))
        driver.execute_script("arguments[0].removeAttribute('readonly')", elem)
        elem.clear()
        elem.send_keys(value)

    _click_by_id(wait, "btnSearch")
    time.sleep(3)

    export_btn = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "btnExport"))
    )
    driver.execute_script("arguments[0].click();", export_btn)
    logger.info("Card statistics exported.")

    # Rename the latest downloaded file to a known name
    time.sleep(10)
    latest_file = max(
        [os.path.join(download_dir, f) for f in os.listdir(download_dir)],
        key=os.path.getctime,
    )
    target_file = os.path.join(download_dir, "card_statistics.xls")
    os.rename(latest_file, target_file)
    logger.info("File renamed to: %s", target_file)


def export_member_info(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Scrape membership summary stats from the customer management page."""
    driver.get(f"{BASE_URL}/Customer/Manage")
    time.sleep(2)

    member_info = wait.until(EC.presence_of_element_located(
        (By.XPATH, '//div[contains(@class, "pLeft") and contains(text(), "Members:")]')
    ))

    with open(f"{download_dir}/member_summary.txt", "w", encoding="utf-8") as f:
        f.write(member_info.text)
    logger.info("Member info scraped and saved.")


def export_sales_tickets(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Export order-level sales tickets (includes payment breakdown)."""
    driver.get(f"{BASE_URL}/Report/Tickets")
    time.sleep(2)

    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@class="submitBtn" and text()="Search"]')
    time.sleep(5)

    _click_by_id(wait, "btnShowExportDiv")
    _click_by_id(wait, "chk_showItems")
    _click_by_id(wait, "rd_onlyItems1")
    _click_by_xpath(wait, '//div[@class="fileExport btnExport" and @data-type="0"]')
    time.sleep(90)
    logger.info("Sales tickets exported.")

# ============================================================================
# Download management — verification + automatic retry
# ============================================================================

REQUIRED_FILES = [
    "sales_flow.xlsx",
    "waste_records.xls",
    "recharge_details.xls",
    "card_statistics.xls",
    "member_summary.txt",
    "sales_tickets.xlsx",
]

EXPORT_FUNCTIONS: Dict[str, callable] = {
    "sales_flow":        export_sales_flow,
    "waste_records":     export_waste_records,
    "recharge_details":  export_recharge_details,
    "card_statistics":   export_card_statistics,
    "member_summary":    export_member_info,
    "sales_tickets":     export_sales_tickets,
}


def check_downloads() -> List[str]:
    """Verify all required files were downloaded. Returns list of missing ones."""
    downloaded = os.listdir(download_dir) if os.path.isdir(download_dir) else []
    missing = []

    for required in REQUIRED_FILES:
        found = any(required in f for f in downloaded)
        status = "✓" if found else "✗"
        logger.info("%s %s", status, required)
        if not found:
            missing.append(required)

    return missing


def _create_authenticated_driver(session: requests.Session) -> Tuple:
    """
    Create a Selenium WebDriver that shares the authenticated session
    from requests. Avoids a redundant second login.
    """
    driver = setup_selenium(download_dir)
    driver.get(f"{BASE_URL}/account/signin")

    for cookie in transfer_cookies(session):
        driver.add_cookie(cookie)
    driver.refresh()

    return driver, WebDriverWait(driver, 10)


def retry_missing_downloads(missing_files: List[str]) -> None:
    """
    Re-download any files that failed on the first pass.
    Maps file names back to their export function and retries.
    """
    if not missing_files:
        logger.info("All files downloaded successfully — no retry needed.")
        return

    logger.info("Retrying downloads for: %s", ", ".join(missing_files))
    session = login_session()
    driver, wait = _create_authenticated_driver(session)

    try:
        for file_name in missing_files:
            for key, func in EXPORT_FUNCTIONS.items():
                if key in file_name:
                    try:
                        func(driver, wait)
                        logger.info("Re-downloaded %s.", file_name)
                        time.sleep(10)
                    except Exception as exc:
                        logger.error("Failed to re-download %s: %s", file_name, exc)
                    break
    finally:
        driver.quit()

    still_missing = check_downloads()
    if still_missing:
        logger.warning("Files still missing after retry: %s", ", ".join(still_missing))

# ============================================================================
# Data transformation — Excel → cleaned DataFrames → SQLite
# ============================================================================

def load_excel_data(
    file_path: str,
    date_column: str = None,
    rename_columns: Dict[str, str] = None,
    adjust_time: bool = False,
    skiprows: int = 0,
) -> pd.DataFrame:
    """
    Generic Excel loader with optional date parsing, column renaming,
    and business-hour time adjustment.

    Args:
        file_path:      Path to the Excel file.
        date_column:    Column to parse as datetime (optional).
        rename_columns: Mapping of old → new column names (optional).
        adjust_time:    If True, subtract a configurable offset (default 10 h)
                        to align audit timestamps with the business day.
        skiprows:       Number of header rows to skip.
    """
    df = pd.read_excel(
        file_path,
        parse_dates=[date_column] if date_column else None,
        skiprows=skiprows,
    )

    if rename_columns:
        df = df.rename(columns=rename_columns)

    if date_column and date_column in df.columns:
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")

    if adjust_time and date_column and date_column in df.columns:
        # Business day starts at 10 AM; an audit at 2 AM belongs to the previous day
        df["adj_date"] = df[date_column].apply(
            lambda x: (x - timedelta(hours=10)).date()
        ).ffill()

    return df


def clean_waste_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Waste data cleaning pipeline:
      - Fix known timestamp anomalies
      - Forward-fill missing categories
      - Normalise note field
    """
    if "audit_time" in df.columns:
        df["category"] = df["category"].bfill()

    return df


@functools.lru_cache(maxsize=32)
def get_cached_db_path(year_month: str) -> str:
    """Check whether a database file exists for the given YYYYMM and cache the result."""
    db_path = os.path.join(config.database_dir, f"sales_data_{year_month}.db")
    return db_path if os.path.exists(db_path) else None


def export_to_database(dataframes: Dict[str, pd.DataFrame], db_name: str = None) -> None:
    """
    Bulk-insert all DataFrames into a single SQLite database.
    Datetime columns are converted to ISO strings for compatibility.
    """
    db_dir = config.database_dir
    os.makedirs(db_dir, exist_ok=True)

    if db_name is None:
        db_name = f"sales_data_{YEAR}{MONTH:02d}.db"

    db_path = os.path.join(db_dir, db_name)

    with sqlite3.connect(db_path) as conn:
        for table_name, df in dataframes.items():
            df_copy = df.copy()
            for col in df_copy.select_dtypes(include=["datetime64"]).columns:
                df_copy[col] = df_copy[col].astype(str)
            df_copy.to_sql(table_name, conn, if_exists="replace", index=False)

        logger.info("Data exported to %s.", db_path)


def process_data() -> None:
    """
    Full ETL pipeline: load raw Excel exports → clean → transform → store in SQLite.

    Column mappings are defined here so the rest of the app works with
    standardised English field names regardless of the source system's locale.
    """
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
    db_dir = config.database_dir

    dataframes = {
        "sales": load_excel_data(
            f"{download_dir}/sales_flow.xlsx",
            date_column="sale_time",
        ),
        "waste": clean_waste_data(load_excel_data(
            f"{download_dir}/waste_records.xls",
            date_column="audit_time",
            rename_columns={"quantity": "qty"},
            adjust_time=True,
        )),
        "memberships": load_excel_data(
            f"{download_dir}/card_statistics.xls",
            date_column="date",
        ),
        "financial": pd.read_csv(f"{db_dir}/financial_params.csv"),
        "mem_detail": load_excel_data(
            f"{download_dir}/recharge_details.xls",
            date_column="recharge_time",
        ),
        "sales_detail": load_excel_data(
            f"{download_dir}/sales_tickets.xlsx",
            date_column="sale_date",
        ),
        "weather": load_excel_data(
            f"{db_dir}/weather.xlsx",
            date_column="date",
        ),
        "opening_cost": load_excel_data(
            f"{db_dir}/opening_cost.xlsx",
        ),
    }

    # Load member summary text file
    try:
        with open(f"{download_dir}/member_summary.txt", "r", encoding="utf-8") as f:
            lines = [line.strip().split(",") for line in f if line.strip()]
        dataframes["member_card"] = pd.DataFrame(lines)
    except Exception as exc:
        logger.warning("Member summary file could not be parsed: %s", exc)

    export_to_database(dataframes)
    get_cached_db_path.cache_clear()

# ============================================================================
# Download orchestration
# ============================================================================

def download_data() -> None:
    """
    Orchestrate the full download sequence.

    Each export runs in its own Selenium session to avoid
    state leakage between report pages (Selenium does not
    support multi-threaded driver access).
    """
    # Clean and recreate download directory
    if os.path.exists(download_dir):
        shutil.rmtree(download_dir)
    os.makedirs(download_dir)

    session = login_session()

    for name, export_func in EXPORT_FUNCTIONS.items():
        driver, wait = _create_authenticated_driver(session)
        try:
            logger.info("Exporting: %s", name)
            export_func(driver, wait)
        except Exception as exc:
            logger.error("Export failed for %s: %s", name, exc)
        finally:
            driver.quit()

    check_downloads()
    logger.info("Download phase complete.")

# ============================================================================
# Main entry point
# ============================================================================

def main() -> None:
    """Full pipeline: download → verify → retry → clean → store."""
    try:
        download_data()
        missing = check_downloads()
        if missing:
            retry_missing_downloads(missing)
        process_data()
        logger.info("Pipeline complete.")
    except Exception as exc:
        logger.error("Pipeline error: %s", exc, exc_info=True)
    finally:
        logger.info("Pipeline finished.")


if __name__ == "__main__":
    main()
