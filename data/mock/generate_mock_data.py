"""
Mock Data Generator - 高保真脱敏合成数据生成器
生成符合 retail/bakery 业务真实分布的 SQLite 月度数据库。
支持全部 9 张标准表：sales, loss, cards, cards_detail, sales_detail, financial, weather, member_card, openning_cost

运行方式：
    python data/mock/generate_mock_data.py
输出：
    database/business_data_YYYYMM.db (覆盖历史与近期月份)
"""
from __future__ import annotations

import calendar
import os
import random
import sqlite3
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_DIR = os.path.join(BASE_DIR, "database")
os.makedirs(DB_DIR, exist_ok=True)

# ── 商品库与分类定义 ─────────────────────────────────────────────────────────────
PRODUCTS = [
    # (商品名称, 商品分类, 收入分类, 原价, 原料成本率)
    ("法式原味可颂", "现烤面包", "现烤", 12.0, 0.32),
    ("海盐芝士吐司", "现烤面包", "现烤", 18.0, 0.30),
    ("日式红豆包", "现烤面包", "现烤", 8.0, 0.28),
    ("法棍面包", "现烤面包", "现烤", 15.0, 0.25),
    ("黑麦全麦欧包", "现烤面包", "现烤", 22.0, 0.33),
    ("碱水牛角包", "现烤面包", "现烤", 14.0, 0.30),
    ("肉松小贝", "精选西点", "西点", 16.0, 0.38),
    ("巴斯克芝士切块", "精选西点", "西点", 28.0, 0.40),
    ("草莓奶油切块", "精选西点", "西点", 32.0, 0.42),
    ("提拉米苏", "精选西点", "西点", 26.0, 0.36),
    ("经典曲奇礼盒", "常温伴手礼", "其他", 45.0, 0.35),
    ("布朗尼蛋糕", "精选西点", "西点", 18.0, 0.34),
    ("生椰拿铁", "咖啡饮品", "饮品", 20.0, 0.20),
    ("美式咖啡", "咖啡饮品", "饮品", 15.0, 0.15),
    ("燕麦拿铁", "咖啡饮品", "饮品", 22.0, 0.22),
    ("白桃乌龙柠檬茶", "咖啡饮品", "饮品", 18.0, 0.20),
    ("6寸动物奶油蛋糕", "生日蛋糕", "蛋糕", 168.0, 0.38),
    ("8寸水果双层蛋糕", "生日蛋糕", "蛋糕", 238.0, 0.40),
]

PAYMENT_METHODS = ["微信支付", "支付宝", "储值卡支付", "现金", "美团券"]
PAYMENT_WEIGHTS = [0.55, 0.25, 0.12, 0.05, 0.03]

SOURCES = ["门店", "自营小程序", "美团", "饿了么"]
SOURCE_WEIGHTS = [0.70, 0.15, 0.10, 0.05]

LOSS_REASONS = ["隔夜过期", "试吃损耗", "制作失误", "运输破损", "员工试吃"]
LOSS_WEIGHTS = [0.50, 0.25, 0.12, 0.08, 0.05]

WEATHER_TYPES = ["晴", "多云", "阴", "小雨", "大雨"]
WEATHER_WEIGHTS = [0.45, 0.25, 0.15, 0.10, 0.05]
WEATHER_IMPACT = {"晴": 1.05, "多云": 1.0, "阴": 0.95, "小雨": 0.82, "大雨": 0.65}


def _pick_hour() -> int:
    """根据零售时段客流分布随机生成小时 (7:00 ~ 21:00)"""
    hours = list(range(7, 22))  # 7 to 21 -> 15 items
    weights = [
        0.02, 0.08, 0.08, 0.06, 0.07,  # 7, 8, 9, 10, 11
        0.11, 0.08, 0.06, 0.07, 0.09,  # 12, 13, 14, 15, 16
        0.12, 0.08, 0.05, 0.02, 0.01   # 17, 18, 19, 20, 21
    ]
    return random.choices(hours, weights=weights)[0]


def generate_month_database(year: int, month: int, db_path: str):
    """为指定年月生成单月完整 SQLite 数据库"""
    num_days = calendar.monthrange(year, month)[1]
    
    sales_rows = []
    loss_rows = []
    cards_rows = []
    cards_detail_rows = []
    sales_detail_rows = []
    weather_rows = []

    cum_member_balance = 120000.0

    for d in range(1, num_days + 1):
        cur_date = date(year, month, d)
        date_str = cur_date.strftime("%Y-%m-%d")
        weekday = cur_date.weekday()
        is_weekend = weekday >= 5

        # 1. 天气数据
        w_type = random.choices(WEATHER_TYPES, weights=WEATHER_WEIGHTS)[0]
        base_temp = 22 + 6 * np.sin((month - 1) * np.pi / 6)
        t_high = round(base_temp + random.uniform(2, 6), 1)
        t_low = round(base_temp - random.uniform(2, 6), 1)
        weather_rows.append({
            "日期": date_str,
            "天气": w_type,
            "最高温": t_high,
            "最低温": t_low,
        })

        # 2. 销售订单生成
        base_orders = random.randint(180, 260) if not is_weekend else random.randint(280, 420)
        base_orders = int(base_orders * WEATHER_IMPACT[w_type])

        day_recharge_total = 0.0
        day_card_spend_total = 0.0

        for order_idx in range(1, base_orders + 1):
            order_id = f"LS{year}{month:02d}{d:02d}-{order_idx:04d}"
            hour = _pick_hour()
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            sale_time_str = f"{date_str} {hour:02d}:{minute:02d}:{second:02d}"
            
            num_items = max(1, int(np.random.poisson(2.2)))
            pay_method = random.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS)[0]
            source = random.choices(SOURCES, weights=SOURCE_WEIGHTS)[0]

            order_orig_total = 0.0
            order_actual_total = 0.0
            order_profit_total = 0.0

            for _ in range(num_items):
                p_name, p_cat, p_income_cat, p_price, p_cost_rate = random.choice(PRODUCTS)
                qty = random.choices([1, 2, 3], weights=[0.8, 0.15, 0.05])[0]
                
                discount_rate = random.choices([0.0, 0.05, 0.10, 0.15], weights=[0.75, 0.15, 0.07, 0.03])[0]
                item_orig = round(p_price * qty, 2)
                item_actual = round(item_orig * (1 - discount_rate), 2)
                item_cost = round(item_actual * p_cost_rate, 2)
                item_profit = round(item_actual - item_cost, 2)

                order_orig_total += item_orig
                order_actual_total += item_actual
                order_profit_total += item_profit

                sales_rows.append({
                    "销售时间": sale_time_str,
                    "流水号": order_id,
                    "商品名称": p_name,
                    "商品分类": p_cat,
                    "收入分类": p_income_cat,
                    "销售数量": qty,
                    "商品原价": p_price,
                    "商品总价": item_orig,
                    "实收金额": item_actual,
                    "成本": item_cost,
                    "利润": item_profit,
                    "支付方式": pay_method,
                    "来源": source,
                    "收银员": "系统收银",
                    "日期": date_str,
                    "小时": hour,
                })

            sales_detail_rows.append({
                "日期": date_str,
                "流水号": order_id,
                "商品原价": order_orig_total,
                "实收金额": order_actual_total,
                "折让金额": round(order_orig_total - order_actual_total, 2),
                "利润": order_profit_total,
                "支付方式": pay_method,
                "商品数量": num_items,
                "商品名称": "混合商品",
                "来源": source,
            })

            if pay_method == "储值卡支付":
                day_card_spend_total += order_actual_total

        # 3. 报损数据生成
        num_loss_items = random.randint(2, 6)
        for _ in range(num_loss_items):
            p_name, p_cat, _, p_price, _ = random.choice(PRODUCTS[:10])
            loss_qty = random.randint(1, 4)
            loss_reason = random.choices(LOSS_REASONS, weights=LOSS_WEIGHTS)[0]
            loss_amt = round(p_price * loss_qty, 2)
            loss_audit_time = f"{date_str} 21:{random.randint(10,50):02d}:00"

            loss_rows.append({
                "审核时间": loss_audit_time,
                "调整日期": date_str,
                "商品名称": p_name,
                "商品分类": p_cat,
                "报废数量": loss_qty,
                "报损金额": loss_amt,
                "金额": loss_amt,
                "报损原因": loss_reason,
                "备注": f"{loss_reason}盘点报废",
            })

        # 4. 储值卡充值
        recharge_tx_count = random.randint(2, 8)
        for _ in range(recharge_tx_count):
            rech_amt = random.choice([100.0, 200.0, 300.0, 500.0, 1000.0])
            gift_amt = round(rech_amt * 0.1, 2) if rech_amt >= 200 else 0.0
            day_recharge_total += rech_amt
            cum_member_balance += (rech_amt + gift_amt)
            rech_time = f"{date_str} {random.randint(9, 20):02d}:{random.randint(0, 59):02d}:00"
            pay_m = random.choice(["微信支付", "支付宝", "现金"])

            cards_detail_rows.append({
                "充值时间": rech_time,
                "日期": date_str,
                "会员卡号": f"CARD-{year}{month:02d}{d:02d}-{len(cards_detail_rows) + 1:04d}",
                "当前剩余金额": round(cum_member_balance, 2),
                "充值金额": rech_amt,
                "赠送金额": gift_amt,
                "支付方式": pay_m,
                "充值门店": "旗舰店",
            })

        cum_member_balance -= day_card_spend_total
        cards_rows.append({
            "日期": date_str,
            "充值总金额": round(day_recharge_total, 2),
            "储值卡消费总金额": round(day_card_spend_total, 2),
            "本金消费金额": round(day_card_spend_total * 0.85, 2),
            "赠送消费金额": round(day_card_spend_total * 0.15, 2),
        })

    # 5. 财务参数
    financial_rows = [{
        "日期": f"{year}-{month:02d}-01",
        "固定支出": 850.0,
        "原料成本比": 0.35,
        "运营管理比": 0.12,
    }]

    # 6. 会员总表
    member_card_rows = [{
        "0": f"会员总数：{1200 + month * 45}",
        "1": f"卡内总余额：{round(cum_member_balance, 2)}（本金：{round(cum_member_balance * 0.82, 2)} 赠送：{round(cum_member_balance * 0.18, 2)}）",
    }]

    # 7. 开业成本
    openning_cost_rows = [
        {"开店项目": "店铺硬装与隔断工程", "类别": "装修工程", "金额": 185000.0, "备注": "含水电暖与消防工程"},
        {"开店项目": "欧洲进口层炉与发酵箱", "类别": "硬件设备", "金额": 128000.0, "备注": "专业烘焙设备"},
        {"开店项目": "风冷蛋糕展示柜与冷库", "类别": "硬件设备", "金额": 56000.0, "备注": "保鲜与后厨冷链"},
        {"开店项目": "意式双头咖啡机与磨豆机", "类别": "硬件设备", "金额": 38000.0, "备注": "水吧配套"},
        {"开店项目": "初次原料物料备货", "类别": "原材料", "金额": 45000.0, "备注": "进口面粉/黄油/包材"},
        {"开店项目": "智能收银与安防监控系统", "类别": "IT与软件", "金额": 18000.0, "备注": "POS与多路高清"},
        {"开店项目": "店面物业押金与首期租金", "类别": "运营资产", "金额": 90000.0, "备注": "押二付一"},
        {"开店项目": "VI品牌设计与开业推广", "类别": "运营资产", "金额": 25000.0, "备注": "开业营销与耗材"},
    ]

    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    pd.DataFrame(sales_rows).to_sql("sales", conn, index=False)
    pd.DataFrame(loss_rows).to_sql("loss", conn, index=False)
    pd.DataFrame(cards_rows).to_sql("cards", conn, index=False)
    pd.DataFrame(cards_detail_rows).to_sql("cards_detail", conn, index=False)
    pd.DataFrame(sales_detail_rows).to_sql("sales_detail", conn, index=False)
    pd.DataFrame(financial_rows).to_sql("financial", conn, index=False)
    pd.DataFrame(weather_rows).to_sql("weather", conn, index=False)
    pd.DataFrame(member_card_rows).to_sql("member_card", conn, index=False)
    pd.DataFrame(openning_cost_rows).to_sql("openning_cost", conn, index=False)
    conn.close()


def generate_all_mock_databases():
    """生成从 2024-09 到 2026-08 的连续月度示例数据库"""
    print(f"正在生成合成数据库至: {DB_DIR}")
    
    months_to_generate = [
        (2024, 9), (2024, 10), (2024, 11), (2024, 12),
        (2025, 1), (2025, 2), (2025, 3), (2025, 4),
        (2025, 5), (2025, 6), (2025, 7), (2025, 8),
        (2025, 9), (2025, 10), (2025, 11), (2025, 12),
        (2026, 1), (2026, 2), (2026, 3), (2026, 4),
        (2026, 5), (2026, 6), (2026, 7), (2026, 8),
    ]

    for y, m in months_to_generate:
        filename = f"business_data_{y}{m:02d}.db"
        db_path = os.path.join(DB_DIR, filename)
        generate_month_database(y, m, db_path)
        print(f"  ✓ 已生成: {filename}")

    # 同时生成一份通用的固定成本 CSV
    csv_path = os.path.join(DB_DIR, "固定成本.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("项目,月度金额,日均金额,备注\n")
        f.write("房租物业,15000,500,商铺核心地段月租\n")
        f.write("员工薪资,8000,266.67,后厨与前厅薪资分摊\n")
        f.write("水电杂费,2500,83.33,高功率烘焙用电与水费\n")

    print("✅ 全部示例合成数据库已成功生成！")


if __name__ == "__main__":
    generate_all_mock_databases()
