"""
数据爬取和处理模块 - 用于从POS系统下载和处理业务数据
"""

from __future__ import annotations

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
from typing import Dict, Tuple

from dotenv import load_dotenv
import pandas as pd
import requests
import yaml
try:  # Selenium is only needed by the legacy browser-based downloader.
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ModuleNotFoundError:  # Keep the requests-only Vercel path lightweight.
    webdriver = Options = Service = By = EC = WebDriverWait = None

# ============================================================================
# 配置管理
# ============================================================================

class ScraperConfig:
    """爬虫配置管理类 — reads config.ini (INI) or config.yaml (YAML)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        self._settings = {}

        # Prefer config.ini (INI format)
        if os.path.exists('config.ini'):
            cp = ConfigParser()
            cp.read('config.ini')
            for section in cp.sections():
                for key, value in cp.items(section):
                    self._settings[f'{section}.{key}'] = value
            for key, value in cp.items('DEFAULT'):
                self._settings[key] = value
            return

        # Fall back to config.yaml
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r', encoding='utf-8') as f:
                yc = yaml.safe_load(f) or {}
            for section, values in yc.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        self._settings[f'{section}.{key}'] = str(value)
            return

    def _get(self, key: str, fallback: str = '') -> str:
        return self._settings.get(key, fallback)

    @property
    def year(self) -> int:
        val = self._get('Year', str(datetime.now().year))
        return int(val) if val.isdigit() else datetime.now().year

    @property
    def month(self) -> int:
        val = self._get('Month', str(datetime.now().month))
        return int(val) if val.isdigit() else datetime.now().month

    @property
    def download_dir(self) -> str:
        return self._get('PATHS.DownloadDir', './data')

    @property
    def database_dir(self) -> str:
        return self._get('PATHS.DatabaseDir', './database')

    @property
    def max_retries(self) -> int:
        val = self._get('RETRY.MaxRetries', '3')
        return int(val) if val.isdigit() else 3


# 全局配置和日志
config = ScraperConfig()
YEAR = config.year
MONTH = config.month
download_dir = config.download_dir

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# ============================================================================
# HTTP 请求配置
# ============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

BASE_URL = "https://beta45.pospal.cn"
LOGIN_URL = f"{BASE_URL}/Account/Signin"

# ============================================================================
# 认证函数
# ============================================================================

def get_credentials() -> Tuple[str, str]:
    """获取登录凭证"""
    username = os.environ.get("POSPAL_USER", "").strip()
    password = os.environ.get("POSPAL_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "真实银豹数据需要设置 POSPAL_USER 和 POSPAL_PASSWORD；"
            "公开演示请使用仓库内的脱敏预热缓存"
        )

    return username, password


def login_session(max_retries: int = None) -> requests.Session:
    """创建并登录会话（带自动重试）"""
    max_retries = max_retries or config.max_retries
    
    for attempt in range(max_retries):
        try:
            username, password = get_credentials()
            session = requests.Session()
            response = session.post(LOGIN_URL, data={'username': username, 'password': password})
            response.raise_for_status()
            logger.info("登录成功")
            return session
        except Exception as e:
            logger.error(f"登录失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise RuntimeError(f"经过 {max_retries} 次重试后登录仍然失败")
            time.sleep(2 ** attempt)


def transfer_cookies(requests_session: requests.Session) -> list:
    """将 requests 的 Cookies 转换为 Selenium 格式"""
    return [{
        'name': c.name,
        'value': c.value,
        'domain': c.domain,
        'path': c.path,
        'secure': c.secure,
        'httpOnly': c.has_nonstandard_attr('HttpOnly'),
    } for c in requests_session.cookies]

# ============================================================================
# Selenium 配置
# ============================================================================

CHROME_DRIVER_PATHS = [
    "/usr/local/bin/chromedriver",
    "/opt/homebrew/bin/chromedriver",
    os.path.expanduser("~/chromedriver")
]


def setup_selenium(download_directory: str = "data") -> webdriver.Chrome:
    """配置并初始化 Chrome WebDriver"""
    if webdriver is None:
        raise RuntimeError("Selenium is not installed; install requirements-legacy.txt")
    options = Options()
    options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(download_directory),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    
    for arg in ['--no-sandbox', '--disable-dev-shm-usage', '--headless', 
                '--disable-gpu', '--window-size=1920,1080']:
        options.add_argument(arg)
    
    # 尝试默认 ChromeDriver
    try:
        return webdriver.Chrome(options=options)
    except Exception as e:
        logger.warning(f"使用默认 ChromeDriver 失败: {e}")
    
    # 尝试指定路径
    for driver_path in CHROME_DRIVER_PATHS:
        if os.path.exists(driver_path):
            try:
                service = Service(executable_path=driver_path)
                driver = webdriver.Chrome(service=service, options=options)
                logger.info(f"成功使用 ChromeDriver: {driver_path}")
                return driver
            except Exception as e:
                logger.warning(f"ChromeDriver {driver_path} 失败: {e}")
    
    raise RuntimeError("无法初始化 Chrome WebDriver")

# ============================================================================
# 日期处理
# ============================================================================

def get_month_range(year: int, month: int) -> Tuple[str, str, int]:
    """获取指定月份的日期范围"""
    _, last_day = calendar.monthrange(year, month)
    start = f"{year}.{month:02d}.01 00:00"
    end = f"{year}.{month:02d}.{last_day} 23:59"
    return start, end, last_day


def set_date_range(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """设置报告日期范围"""
    start_str, end_str, _ = get_month_range(YEAR, MONTH)
    
    wait.until(EC.element_to_be_clickable((By.ID, "dateTimeRangeBox"))).click()

    for xpath, value in [
        ('//input[contains(@id, "ui-timePicker-begin-")]', start_str),
        ('//input[contains(@id, "ui-timePicker-end-")]', end_str)
    ]:
        input_elem = driver.find_element(By.XPATH, xpath)
        driver.execute_script("arguments[0].removeAttribute('readonly')", input_elem)
        input_elem.clear()
        input_elem.send_keys(value)
    
    logger.info(f"日期范围: {start_str} - {end_str}")

# ============================================================================
# 导出函数
# ============================================================================

def _click_element(wait: WebDriverWait, locator: tuple, timeout: int = 10) -> None:
    """等待并点击元素"""
    wait.until(EC.element_to_be_clickable(locator)).click()


def _click_by_id(wait: WebDriverWait, element_id: str) -> None:
    """通过 ID 点击元素"""
    _click_element(wait, (By.ID, element_id))


def _click_by_xpath(wait: WebDriverWait, xpath: str) -> None:
    """通过 XPath 点击元素"""
    _click_element(wait, (By.XPATH, xpath))


def export_sales_flow(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """导出商品销售流水"""
    driver.get(f"{BASE_URL}/Report/ProductSaleDetails")
    time.sleep(2)
    
    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@p-click="search" and contains(@class, "submitBtn")]')
    time.sleep(8)
    
    _click_by_id(wait, "btnExport")
    time.sleep(30)
    logger.info("商品销售流水已导出")


def export_loss_records(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """导出商品报损记录"""
    driver.get(f"{BASE_URL}/Inventory/DiscardInventoryHistory")
    time.sleep(2)
    
    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@class="submitBtn" and text()="查询"]')
    time.sleep(3)
    
    _click_by_id(wait, "btnExportDiscardInventoryHistory")
    _click_by_id(wait, "ck_showItems")
    _click_by_xpath(wait, '//div[@class="fileExport btnExport" and @p-click="export"]')
    time.sleep(10)
    logger.info("商品报损记录已导出")


def export_recharge_details(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """导出充值明细"""
    driver.get(f"{BASE_URL}/CardReport/RechargeLogs")
    time.sleep(2)
    
    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@class="submitBtn" and text()="查询"]')
    time.sleep(3)
    
    _click_by_id(wait, "btnExport")
    logger.info("充值明细已导出")


def export_card_statistics(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """导出储值卡数据统计"""
    driver.get(f"{BASE_URL}/CustomerReport/RechargeAndConsumptionSummary")
    time.sleep(2)

    _, _, last_day = get_month_range(YEAR, MONTH)
    start_date = f"{YEAR}-{MONTH:02d}-01"
    end_date = f"{YEAR}-{MONTH:02d}-{last_day}"

    for elem_id, value in [("txt_startDatetime", start_date), ("txt_endDatetime", end_date)]:
        elem = wait.until(EC.element_to_be_clickable((By.ID, elem_id)))
        driver.execute_script("arguments[0].removeAttribute('readonly')", elem)
        elem.clear()
        elem.send_keys(value)
        logger.info(f"{elem_id} 设置为: {value}")

    _click_by_id(wait, "btnSearch")
    time.sleep(3)

    export_btn = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "btnExport")))
    driver.execute_script("arguments[0].click();", export_btn)
    logger.info("储值卡数据统计已导出")
    
    # 重命名下载的文件
    time.sleep(10)
    latest_file = max(
        [os.path.join(download_dir, f) for f in os.listdir(download_dir)],
        key=os.path.getctime
    )
    target_file = os.path.join(download_dir, "储值卡数据统计.xls")
    os.rename(latest_file, target_file)
    logger.info(f"文件已重命名: {target_file}")


def export_member_info(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """导出会员储值信息"""
    driver.get(f"{BASE_URL}/Customer/Manage")
    time.sleep(2)

    member_info = wait.until(EC.presence_of_element_located(
        (By.XPATH, '//div[contains(@class, "pLeft") and contains(text(), "会员数：")]')
    ))
    
    with open(f"{download_dir}/会员储值.txt", "w", encoding="utf-8") as f:
        f.write(member_info.text)
    logger.info(f"会员储值信息已保存")


def export_sales_tickets(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """导出销售单据"""
    driver.get(f"{BASE_URL}/Report/Tickets")
    time.sleep(2)
    
    set_date_range(driver, wait)
    _click_by_xpath(wait, '//div[@class="submitBtn" and text()="查询"]')
    time.sleep(5)
    
    _click_by_id(wait, "btnShowExportDiv")
    _click_by_id(wait, "chk_showItems")
    _click_by_id(wait, "rd_onlyItems1")
    _click_by_xpath(wait, '//div[@class="fileExport btnExport" and @data-type="0"]')
    time.sleep(90)
    logger.info("销售单据已导出")

# ============================================================================
# 下载管理
# ============================================================================

REQUIRED_FILES = [
    "商品销售流水.xlsx",
    "商品报损记录.xls",
    "充值明细.xls",
    "储值卡数据统计.xls",
    "会员储值.txt",
    "销售流水单据.xlsx"
]

EXPORT_FUNCTIONS = {
    "商品销售流水": export_sales_flow,
    "商品报损记录": export_loss_records,
    "充值明细": export_recharge_details,
    "储值卡数据统计": export_card_statistics,
    "会员储值": export_member_info,
    "销售流水单据": export_sales_tickets,
}


def check_downloads() -> list:
    """检查文件下载状态，返回缺失文件列表"""
    downloaded = os.listdir(download_dir)
    missing = []
    
    for required in REQUIRED_FILES:
        found = any(required in f for f in downloaded)
        status = "✓" if found else "✗"
        logger.info(f"{status} {required}")
        if not found:
            missing.append(required)
    
    return missing


def _create_authenticated_driver(session: requests.Session) -> tuple:
    """创建已认证的 driver 和 wait 实例"""
    driver = setup_selenium(download_dir)
    driver.get(f"{BASE_URL}/account/signin")
    
    for cookie in transfer_cookies(session):
        driver.add_cookie(cookie)
    driver.refresh()
    
    return driver, WebDriverWait(driver, 10)


def retry_missing_downloads(missing_files: list) -> None:
    """重新下载缺失的文件"""
    if not missing_files:
        logger.info("所有文件下载成功，无需重试")
        return
    
    logger.info(f"重新下载缺失文件: {', '.join(missing_files)}")
    session = login_session()
    driver, wait = _create_authenticated_driver(session)
    
    try:
        for file_name in missing_files:
            for key, func in EXPORT_FUNCTIONS.items():
                if key in file_name:
                    try:
                        func(driver, wait)
                        logger.info(f"重新下载 {file_name} 完成")
                        time.sleep(10)
                    except Exception as e:
                        logger.error(f"重新下载 {file_name} 失败: {e}")
                    break
    finally:
        driver.quit()
    
    still_missing = check_downloads()
    if still_missing:
        logger.warning(f"文件仍然缺失: {', '.join(still_missing)}")

# ============================================================================
# 数据处理
# ============================================================================

def load_excel_data(file_path: str, date_column: str = None, 
                    rename_columns: dict = None, adjust_time: bool = False,
                    skiprows: int = 0) -> pd.DataFrame:
    """通用 Excel 数据加载函数"""
    df = pd.read_excel(
        file_path,
        parse_dates=[date_column] if date_column else None,
        skiprows=skiprows
    )
    
    if rename_columns:
        df = df.rename(columns=rename_columns)
    
    if date_column and date_column in df.columns:
        df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
    
    if adjust_time and date_column:
        df['调整日期'] = df[date_column].apply(
            lambda x: (x - timedelta(hours=10)).date()
        ).ffill()
    
    return df


def clean_loss_data(df: pd.DataFrame) -> pd.DataFrame:
    """清理报损数据"""
    mask = df['审核时间'].dt.strftime('%Y-%m-%d %H').eq('2025-03-25 16')
    if mask.any():
        df.loc[mask, '审核时间'] = df.loc[mask, '审核时间'].apply(
            lambda x: x.replace(hour=3)
        )
    
    df['商品分类'] = df['商品分类'].bfill()
    remarks = df['备注'].astype('string')
    df.loc[remarks.str.contains('报损', na=False), '备注'] = df['商品分类']
    return df


@functools.lru_cache(maxsize=32)
def get_cached_db_path(year_month: str) -> str:
    """缓存数据库路径检查"""
    db_path = os.path.join(config.database_dir, f'business_data_{year_month}.db')
    return db_path if os.path.exists(db_path) else None


def export_to_database(dataframes: Dict[str, pd.DataFrame], db_name: str = None) -> None:
    """导出数据到 SQLite 数据库"""
    db_dir = config.database_dir
    os.makedirs(db_dir, exist_ok=True)
    
    if db_name is None:
        db_name = f'business_data_{YEAR}{MONTH:02d}.db'
    
    db_path = os.path.join(db_dir, db_name)
    
    with sqlite3.connect(db_path) as conn:
        for table_name, df in dataframes.items():
            df_copy = df.copy()
            for col in df_copy.select_dtypes(include=['datetime64']).columns:
                df_copy[col] = df_copy[col].astype(str)
            df_copy.to_sql(table_name, conn, if_exists='replace', index=False)
        logger.info(f"数据已导出到 {db_path}")


def process_data() -> None:
    """处理并导出数据"""
    warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
    db_dir = config.database_dir
    
    # 加载数据
    dataframes = {
        'sales': load_excel_data(f'{download_dir}/商品销售流水.xlsx', date_column='销售时间'),
        'loss': clean_loss_data(load_excel_data(
            f'{download_dir}/商品报损记录.xls',
            date_column='审核时间',
            rename_columns={'数量': '报废数量'},
            adjust_time=True
        )),
        'cards': load_excel_data(f'{download_dir}/储值卡数据统计.xls', date_column='日期'),
        'financial': pd.read_csv(f'{db_dir}/固定成本.csv'),
        'cards_detail': load_excel_data(f'{download_dir}/充值明细.xls', date_column='充值时间'),
        'sales_detail': load_excel_data(f'{download_dir}/销售流水单据.xlsx', date_column='日期'),
        'weather': load_excel_data(f'{db_dir}/天气.xlsx', date_column='日期'),
        'openning_cost': load_excel_data(f'{db_dir}/开店成本.xlsx'),
    }
    
    # 加载会员储值信息
    try:
        with open(f'{download_dir}/会员储值.txt', 'r', encoding='utf-8') as f:
            lines = [line.strip().split(',') for line in f if line.strip()]
        dataframes['member_card'] = pd.DataFrame(lines)
    except Exception as e:
        logger.warning(f"会员储值文件处理失败: {e}")

    export_to_database(dataframes)
    get_cached_db_path.cache_clear()

# ============================================================================
# 下载流程
# ============================================================================

def download_data() -> None:
    """下载所有数据"""
    # 清理并创建下载目录
    if os.path.exists(download_dir):
        shutil.rmtree(download_dir)
    os.makedirs(download_dir)

    session = login_session()

    download_mode = os.environ.get("POSPAL_DOWNLOAD_MODE", "auto").lower()
    if download_mode in {"auto", "webapi", "direct"}:
        try:
            from modules.pospal_webapi import download_reports_via_webapi

            download_reports_via_webapi(session, BASE_URL, HEADERS, download_dir, YEAR, MONTH)
            missing = check_downloads()
            if not missing:
                logger.info("直接接口下载完成")
                return
            logger.warning("直接接口下载后仍缺失文件: %s", ", ".join(missing))
            if download_mode in {"webapi", "direct"}:
                raise RuntimeError("直接接口下载不完整")
        except Exception as e:
            if download_mode in {"webapi", "direct"}:
                raise
            logger.warning("直接接口下载失败，回退 Selenium: %s", e)

    # 顺序执行所有导出任务（Selenium 不支持多线程共享 driver）
    for name, export_func in EXPORT_FUNCTIONS.items():
        driver, wait = _create_authenticated_driver(session)
        try:
            logger.info(f"开始导出: {name}")
            export_func(driver, wait)
        except Exception as e:
            logger.error(f"导出 {name} 失败: {e}")
        finally:
            driver.quit()
    
    check_downloads()
    logger.info("数据下载完成")

# ============================================================================
# 主函数
# ============================================================================

def main() -> None:
    """主函数"""
    try:
        download_data()
        missing = check_downloads()
        if missing:
            retry_missing_downloads(missing)
        process_data()
        logger.info("数据处理完成")
    except Exception as e:
        logger.error(f"程序执行出错: {e}", exc_info=True)
    finally:
        logger.info("程序执行结束")


if __name__ == "__main__":
    main()
