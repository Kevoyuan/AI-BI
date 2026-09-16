"""LangGraph-based AI assistant for the AI-BI Web Dashboard.

The browser sends the current dashboard context and question to the server. A
LangGraph tool-calling loop can answer from that context, fetch other PosPal
ranges, run parameterized analyses, or query a specific product when needed.
"""
from __future__ import annotations

import logging
import math
import os
import re
from datetime import date, datetime, timezone
from typing import Annotated, Any, AsyncGenerator, Dict, List, Sequence, Tuple, TypedDict

logger = logging.getLogger("ai_assistant")

try:
    from langchain_core.messages import (
        AIMessage,
        AIMessageChunk,
        BaseMessage,
        HumanMessage,
        SystemMessage,
    )
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import START, StateGraph
    from langgraph.graph.message import add_messages
    from langgraph.prebuilt import ToolNode, tools_condition
except Exception as exc:  # pragma: no cover - import guard
    logger.warning("LangGraph/OpenAI 依赖未安装，AI 助手不可用: %s", exc)
    raise


SYSTEM_TEMPLATE = """你是一家连锁烘焙/餐饮门店（AI-BI 智能商业分析平台）的资深经营分析专家与智能决策助手。
下面是你当前正在查看的看板数据快照。请用简洁、可执行的中文回答店主的问题：
- 解释指标含义与变化
- 指出异常、风险与机会
- 给出具体、低成本的行动建议
- 金额优先用「万」或具体数值，保持口语化、像真人店长对话
- 不知道就说不知道，不要编造数据
- 不输出与经营无关的闲聊

【数据工具】
你有一个工具 fetch_pospal_data，可以拉取银豹(PosPal)后台任意月份、日期、时间段
的经营数据（销售、报损、储值、会员、天气等），且自带缓存不会重复打接口。
- 若用户问的**不在当前看板时间范围内**（其他月份 / 具体日期 / 跨日期区间），
  请先调用 fetch_pospal_data 拉取对应数据，再基于真实数据回答，不要凭空编造。
- 若用户问的就在当前看板范围内，直接基于下方快照回答即可，不必调用工具。
- 调用 fetch_pospal_data 时 date_spec 支持字典或字符串（如 "2026-06"、"2026-07"、"month" 等）。
- 默认 scope="digest"（预压缩文本，最省 token）；**只有画图时才用 scope="chart"**
  （精简数组）；不要用 scope="full"/"raw" 除非要追原始明细。
- 若店主要求把某月数据长期保存（如要跨年对比），调用工具时置 archive=True。

【分析工具】
你还有工具 run_analysis，做六类参数化分析（不写代码）：
- 预测备货：run_analysis(analysis="forecast", date_spec=..., horizon="tomorrow"|"next_week")
  → 明天/下周销售额预测。预测是参考值，回答时用"预计/大约"措辞并给出置信区间。
- 天气影响：run_analysis(analysis="weather", date_spec=...) → 天气实况、历史影响系数和预警。
- 购物篮连带：run_analysis(analysis="basket", date_spec=..., target_product="...") →
  全店平均连带率、多件单占比、TOP 共购商品搭配。
- 时段客流潮汐：run_analysis(analysis="hourly", date_spec=...) →
  各小时营收、订单量(TC)、客单价(AC)及波峰占比。
- 商品ABC与滞销诊断：run_analysis(analysis="abc", date_spec=...) →
  A/B/C 商品结构及滞销淘汰候选商品。
- 储值健康度：run_analysis(analysis="recharge", date_spec=...) →
  现金进账、储值卡消耗、新增充值金额与档位分布。
- date_spec 与 fetch_pospal_data 相同；结果可直接转成 chart spec 出图。

【单品明细查询工具】
你有专门查询单品的工具 query_product_sales(product_name="...", date_spec=..., by_barcode=True)。
- 当店主询问**某个具体商品、单品名称或单品表现**（例如“马卡龙这两个月卖得怎么样”、“生吐司最近销量”）时，**必须优先调用 query_product_sales**。
- 严禁仅凭下方看板快照（会截断商品榜单）或 ABC 汇总就断言某个具体单品的真实全量销量。
- 工具会按商品条码自动合并同一商品改名前后的名称，并返回名称/条码拆分、月度走势及报损情况。
- 若 has_name_alias=True，应清晰说明总销量以及名称变迁，并结合报损给出销售或备货建议。

【工具调用行为规范】
1. 需要调用工具时，直接发起工具调用，不要同时输出“正在查询”等占位文本。
2. 工具返回后，立刻基于真实数据给出完整经营诊断与行动建议。

【可视化与富工件（Artifacts）渲染支持】
前端原生支持多种经营分析工件，适时使用：
1. 交互图表 (```chart 或 ```echarts)：type 支持 line / bar / hbar / pie / gauge / scatter；高级需求可直接给 ECharts option（纯 JSON，禁止函数）。
2. 核心指标卡组 (```metrics)：展示 2~4 个关键 KPI 与涨跌幅。
3. 方案对比卡 (```compare)：展示优化前后或两个方案的结构化对比。
4. 经营行动清单 (```checklist 或 Markdown `- [ ]`)。
5. 提示/预警呼出框 (GitHub Alert 语法或 ```callout)。
6. 结构化数据表 (Markdown Table)。

{context}

{domain}
"""


DOMAIN_KNOWLEDGE = """【经营领域知识（判断参考，勿当绝对真理）】
- 术语口径：TC=来客数（流水号去重）；AC=客单价（实收金额/TC）；报废率=报损金额/实收金额；
  试吃=备注或报损原因含「试吃」的项目，不计入经营报废；
  连带率=单据平均商品件数；多件单占比=购买件数>1的单据比例；净利润=实收金额-原料成本-运营管理-固定支出。
- 参考阈值：连带率 <1.4 可提示加强组合推荐；储值卡消耗占比 >50% 且当期新充值低时提示现金流风险；
  报损率 >5% 值得预警、>8% 警告；客单价波动 >15% 关注；单日销售额低于近期均值 2 个标准差可视为高危异常。
- 解读要点：关注周节律、时段潮汐、C 类长尾商品的持续低销量、恶劣天气对到店与外卖结构的影响，
  客单价可通过高频共购组合与收银台加购提升。"""


class AIState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: str
    question: str


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        if abs(value) >= 10000:
            return f"¥{value / 10000:.2f}万"
        if abs(value) >= 100:
            return f"¥{value:,.0f}"
        return f"{value:g}"
    return str(value)


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


_CONTEXT_CACHE: Dict[Tuple[str, str], str] = {}
_MAX_CONTEXT_CACHE = 32


def clear_context_cache() -> None:
    _CONTEXT_CACHE.clear()


def build_context_from_payload(payload: Dict[str, Any] | None) -> str:
    """Compress dashboard JSON into a small business snapshot for the LLM."""
    if not payload:
        return "（暂无看板数据，请先加载经营数据）"

    meta = payload.get("meta") or {}
    range_str = str(meta.get("range") or "")
    generated_at = str(meta.get("generatedAt") or "")
    if range_str and generated_at:
        cached = _CONTEXT_CACHE.get((range_str, generated_at))
        if cached is not None:
            return cached

    parts: List[str] = []
    if meta.get("range"):
        parts.append(f"## 当前时间范围：{meta.get('range')}（数据来源：{meta.get('source')}）")

    kpis = payload.get("kpis") or {}
    if kpis:
        items = [
            ("实收金额", kpis.get("revenue")),
            ("订单数", kpis.get("orders")),
            ("客单价", kpis.get("ticket")),
            ("报损金额", kpis.get("loss")),
            ("储值卡消费", kpis.get("cardConsume")),
            ("充值金额", kpis.get("recharge")),
            ("净利润(估算)", kpis.get("netProfit")),
            ("净利润率", kpis.get("netProfitRate")),
        ]
        line = "，".join(f"{key}={_fmt_money(value)}" for key, value in items if value is not None)
        parts.append(f"### 核心 KPI：{line}")

    alerts = payload.get("alerts") or []
    if alerts:
        text = "；".join(f"[{item.get('level', '')}]{item.get('title', '')}" for item in alerts[:6])
        parts.append(f"### 业务提醒：{text}")

    top_products = payload.get("topProducts") or []
    if top_products:
        text = "，".join(
            f"{item.get('name')}({_fmt_money(item.get('amount'))})" for item in top_products[:8]
        )
        parts.append(f"### 热销商品 TOP：{text}")

    category_margin = payload.get("categoryMargin") or []
    if category_margin:
        text = "，".join(
            f"{item.get('category')}(毛利率{_fmt_pct(item.get('margin'))})"
            for item in category_margin[:6]
        )
        parts.append(f"### 分类毛利：{text}")

    weekday_pattern = payload.get("weekdayPattern") or []
    if weekday_pattern:
        text = "，".join(
            f"{item.get('weekday')}:{_fmt_money(item.get('revenue'))}"
            for item in weekday_pattern[:7]
        )
        parts.append(f"### 周节律(各星期营收)：{text}")

    efficiency = payload.get("efficiency") or {}
    if efficiency:
        try:
            text = "，".join(
                f"{key}={_fmt_money(value)}"
                for key, value in efficiency.items()
                if value is not None
            )
            if text:
                parts.append(f"### 经营效率：{text}")
        except Exception:
            pass

    slow_movers = payload.get("slowMovers") or []
    if slow_movers:
        text = "，".join(str(item.get("name")) for item in slow_movers[:5])
        parts.append(f"### 滞销商品：{text}")

    result = "\n".join(parts)
    if range_str and generated_at:
        if len(_CONTEXT_CACHE) >= _MAX_CONTEXT_CACHE:
            _CONTEXT_CACHE.pop(next(iter(_CONTEXT_CACHE)))
        _CONTEXT_CACHE[(range_str, generated_at)] = result
    return result


def _build_system_prompt(context: str) -> str:
    return SYSTEM_TEMPLATE.replace("{context}", context).replace(
        "{domain}", DOMAIN_KNOWLEDGE
    )


def _parse_date_spec(spec: Any) -> Any:
    from modules.dashboard_api import DashboardQuery

    if isinstance(spec, DashboardQuery):
        return spec
    if isinstance(spec, str):
        value = spec.strip()
        if value in ("today", "yesterday", "week", "month"):
            return DashboardQuery.from_preset(value)
        match = re.match(r"^(\d{4})[-/年](\d{1,2})月?$", value)
        if match:
            return DashboardQuery(year=int(match.group(1)), month=int(match.group(2)))
        match = re.match(r"^(\d{1,2})月$", value)
        if match:
            today = date.today()
            return DashboardQuery(year=today.year, month=int(match.group(1)))
        match = re.match(
            r"^(\d{4})[-/年](\d{1,2})月?\s*(?:[~至到,]|to)\s*(\d{4})[-/年](\d{1,2})月?$",
            value,
        )
        if match:
            y1, m1, y2, m2 = map(int, match.groups())
            start = date(y1, m1, 1)
            end = date(y2, m2, 28)
            while end.month == m2:
                end = end.fromordinal(end.toordinal() + 1)
            end = end.fromordinal(end.toordinal() - 1)
            if start > end:
                start, end = end, start
            return DashboardQuery(
                year=start.year,
                month=start.month,
                date_from=start.isoformat(),
                date_to=end.isoformat(),
            )
        match = re.match(
            r"^(\d{4}-\d{2}-\d{2})\s*(?:[~至到,]|to)\s*(\d{4}-\d{2}-\d{2})$",
            value,
        )
        if match:
            start_text, end_text = match.group(1), match.group(2)
            start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
            if start > end:
                start, end = end, start
            return DashboardQuery(
                year=start.year,
                month=start.month,
                date_from=start.isoformat(),
                date_to=end.isoformat(),
            )
        match = re.match(r"^(\d{4}-\d{2}-\d{2})$", value)
        if match:
            d = date.fromisoformat(match.group(1))
            return DashboardQuery(year=d.year, month=d.month, date_from=d.isoformat(), date_to=d.isoformat())
        return DashboardQuery.current()

    if isinstance(spec, dict):
        if "preset" in spec:
            return DashboardQuery.from_preset(str(spec["preset"]))
        if "year" in spec and "month" in spec:
            return DashboardQuery(year=int(spec["year"]), month=int(spec["month"]))
        if spec.get("date_from") and spec.get("date_to"):
            start = date.fromisoformat(str(spec["date_from"]))
            end = date.fromisoformat(str(spec["date_to"]))
            if start > end:
                start, end = end, start
            return DashboardQuery(
                year=start.year,
                month=start.month,
                date_from=start.isoformat(),
                date_to=end.isoformat(),
            )
    return DashboardQuery.current()


@tool
def fetch_pospal_data(
    date_spec: Any,
    scope: str = "digest",
    refresh: bool = False,
    archive: bool = False,
) -> dict:
    """拉取银豹(PosPal)经营后台的实时/历史数据。"""
    from modules.dashboard_api import get_dashboard_payload
    from modules.pospal_live_data import archive_month

    query = _parse_date_spec(date_spec)
    payload = get_dashboard_payload(query, force_refresh=bool(refresh))
    if archive:
        for year, month in _covered_months(query):
            try:
                archive_month(year, month)
            except Exception as exc:
                logger.warning("归档月份 %d-%02d 失败: %s", year, month, exc)
    return _trim_payload(payload, scope)


def _covered_months(query: Any) -> List[Tuple[int, int]]:
    if query.date_from and query.date_to:
        start = date.fromisoformat(query.date_from)
        end = date.fromisoformat(query.date_to)
    else:
        start = date(query.year, query.month, 1)
        end = date(query.year, query.month, 28)
    months: List[Tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def _trim_payload(payload: Dict[str, Any], scope: str) -> Dict[str, Any]:
    if scope == "full":
        return payload
    if scope == "raw":
        return {"meta": payload.get("meta", {}), "raw": payload.get("raw", payload)}
    if scope == "digest":
        return {"meta": payload.get("meta", {}), "digest": build_context_from_payload(payload)}
    if scope == "chart":
        out: Dict[str, Any] = {"meta": payload.get("meta", {})}
        if payload.get("kpis"):
            out["kpis"] = payload["kpis"]
        for key, limit in (
            ("daily", 60),
            ("hourly", 24),
            ("productABC", 30),
            ("slowMovers", 15),
            ("paymentMix", 10),
            ("weekdayPattern", 7),
            ("categoryMargin", 10),
            ("topProducts", 15),
            ("alerts", 10),
            ("kpiDeltas", 10),
        ):
            value = payload.get(key)
            if isinstance(value, list):
                out[key] = value[:limit]
            elif value is not None:
                out[key] = value
        return out
    summary_keys = [
        "meta",
        "kpis",
        "alerts",
        "daily",
        "topProducts",
        "productABC",
        "slowMovers",
        "paymentMix",
        "categoryMargin",
        "weekdayPattern",
        "weatherDaily",
        "memberSummary",
        "efficiency",
    ]
    return {key: payload[key] for key in summary_keys if key in payload}


@tool
def run_analysis(
    analysis: str,
    date_spec: Any = None,
    horizon: str = "tomorrow",
    target_product: str | None = None,
    top_n: int = 10,
) -> dict:
    """运行参数化经营分析（预测/天气/购物篮/时段/ABC/储值）。"""
    if analysis not in ("forecast", "weather", "basket", "hourly", "abc", "recharge"):
        raise ValueError("analysis 必须是 forecast、weather、basket、hourly、abc 或 recharge")
    if analysis == "forecast" and horizon not in ("tomorrow", "next_week"):
        raise ValueError("horizon 必须是 tomorrow 或 next_week")
    try:
        from modules.analysis_tools import (
            run_basket_analysis,
            run_forecast,
            run_hourly_traffic,
            run_product_abc,
            run_recharge_health,
            run_weather_impact,
        )

        if analysis == "weather":
            return run_weather_impact(date_spec)
        if analysis == "forecast":
            return run_forecast(date_spec, horizon)
        if analysis == "basket":
            return run_basket_analysis(date_spec, target_product=target_product, top_n=top_n)
        if analysis == "hourly":
            return run_hourly_traffic(date_spec)
        if analysis == "abc":
            return run_product_abc(date_spec)
        return run_recharge_health(date_spec)
    except Exception as exc:
        logger.warning("分析工具 %s 执行异常: %s", analysis, exc)
        return {"analysis": analysis, "error": f"分析执行异常: {exc}"}


@tool
def query_product_sales(
    product_name: str,
    date_spec: Any = None,
    by_barcode: bool = True,
) -> dict:
    """精确/模糊查询特定商品的销售、改名同码合并、走势与报损数据。"""
    try:
        from modules.analysis_tools import query_product_sales as _query_sales

        return _query_sales(product_name, date_spec=date_spec, by_barcode=by_barcode)
    except Exception as exc:
        logger.warning("单品查询工具 query_product_sales 执行异常: %s", exc)
        return {"found": False, "error": f"单品查询异常: {exc}"}


TOOLS = [fetch_pospal_data, run_analysis, query_product_sales]


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return value if math.isfinite(value) and value >= 0 else default
    except (TypeError, ValueError):
        return default


def _configured_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-flash")


def _pricing_period(at: datetime | None = None) -> str:
    """DeepSeek peak pricing: weekdays 01:00-04:00 and 06:00-10:00 UTC."""
    moment = at or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    utc = moment.astimezone(timezone.utc)
    peak = utc.weekday() < 5 and ((1 <= utc.hour < 4) or (6 <= utc.hour < 10))
    return "peak" if peak else "off_peak"


_LLM_CACHE: Dict[Tuple[str, str, str, float, int], Any] = {}
_BOUND_LLM_CACHE: Dict[Tuple[str, str, str, float, int], Tuple[Any, Any]] = {}


def clear_llm_cache() -> None:
    _LLM_CACHE.clear()
    _BOUND_LLM_CACHE.clear()


def _llm_cache_key() -> Tuple[str, str, str, float, int]:
    return (
        os.getenv("DEEPSEEK_API_KEY", ""),
        os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        _configured_model(),
        max(1.0, _env_float("DEEPSEEK_TIMEOUT_SECONDS", 300.0)),
        max(0, int(_env_float("DEEPSEEK_MAX_RETRIES", 2.0))),
    )


def _build_llm() -> "ChatOpenAI":
    api_key, base_url, model, timeout, max_retries = _llm_cache_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，AI 助手不可用")
    cache_key = (api_key, base_url, model, timeout, max_retries)
    cached = _LLM_CACHE.get(cache_key)
    if cached is not None and type(cached) is ChatOpenAI:
        return cached
    client = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
        temperature=0.3,
        max_tokens=1500,
        timeout=timeout,
        max_retries=max_retries,
    )
    _LLM_CACHE[cache_key] = client
    return client


def _get_bound_llm() -> Any:
    llm = _build_llm()
    cache_key = _llm_cache_key()
    cached = _BOUND_LLM_CACHE.get(cache_key)
    if cached is not None and cached[0] is llm:
        return cached[1]
    bound = llm.bind_tools(TOOLS)
    _BOUND_LLM_CACHE[cache_key] = (llm, bound)
    return bound


def _extract_usage(chunk: AIMessageChunk) -> Dict[str, int]:
    usage = getattr(chunk, "usage_metadata", None) or {}
    response = getattr(chunk, "response_metadata", None) or {}
    response_usage = response.get("token_usage") or response.get("usage") or {}

    def integer(*values: Any) -> int:
        for value in values:
            try:
                if value is not None:
                    return max(0, int(value))
            except (TypeError, ValueError):
                continue
        return 0

    input_details = usage.get("input_token_details") or {}
    prompt_details = response_usage.get("prompt_tokens_details") or {}
    return {
        "input_tokens": integer(
            usage.get("input_tokens"),
            usage.get("prompt_tokens"),
            response_usage.get("input_tokens"),
            response_usage.get("prompt_tokens"),
        ),
        "output_tokens": integer(
            usage.get("output_tokens"),
            usage.get("completion_tokens"),
            response_usage.get("output_tokens"),
            response_usage.get("completion_tokens"),
        ),
        "cached_input_tokens": integer(
            input_details.get("cache_read"),
            input_details.get("cached_tokens"),
            prompt_details.get("cached_tokens"),
            response_usage.get("cached_tokens"),
        ),
    }


def _usage_summary(usage: Dict[str, int]) -> Dict[str, Any]:
    """Return a stable token/cost ledger event for the frontend."""
    model = _configured_model()
    input_tokens = max(0, int(usage.get("input_tokens", 0)))
    output_tokens = max(0, int(usage.get("output_tokens", 0)))
    cached_tokens = min(input_tokens, max(0, int(usage.get("cached_input_tokens", 0))))
    uncached_tokens = max(0, input_tokens - cached_tokens)

    period = _pricing_period()
    flash_defaults = {
        "off_peak": {"input": 0.15, "cached": 0.003, "output": 0.60},
        "peak": {"input": 0.30, "cached": 0.006, "output": 1.20},
    }[period]
    input_rate = _env_float("DEEPSEEK_INPUT_USD_PER_MILLION", flash_defaults["input"])
    cached_rate = _env_float("DEEPSEEK_CACHED_INPUT_USD_PER_MILLION", flash_defaults["cached"])
    output_rate = _env_float("DEEPSEEK_OUTPUT_USD_PER_MILLION", flash_defaults["output"])
    input_cost = (uncached_tokens * input_rate + cached_tokens * cached_rate) / 1_000_000
    uncached_cost = input_tokens * input_rate / 1_000_000
    output_cost = output_tokens * output_rate / 1_000_000
    return {
        "model": model,
        "inputTokens": input_tokens,
        "cachedInputTokens": cached_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
        "cacheHit": cached_tokens > 0,
        "costUsd": round(input_cost + output_cost, 8),
        "cacheSavingsUsd": round(max(0.0, uncached_cost - input_cost), 8),
        "priceVersion": os.getenv("DEEPSEEK_PRICE_VERSION", "2026-09-10"),
        "pricingPeriod": period,
        "ratesUsdPerMillion": {
            "input": input_rate,
            "cachedInput": cached_rate,
            "output": output_rate,
        },
    }


async def _answer_node(state: AIState) -> Dict[str, Any]:
    llm = _get_bound_llm()
    messages: List[BaseMessage] = [SystemMessage(content=_build_system_prompt(state["context"]))]
    messages.extend(state["messages"])
    response = await llm.ainvoke(messages)
    return {"messages": [response]}


_CHECKPOINTER = MemorySaver()


def _build_graph(checkpointer: Any = None):
    graph = StateGraph(AIState)
    graph.add_node("answer", _answer_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "answer")
    graph.add_conditional_edges("answer", tools_condition)
    graph.add_edge("tools", "answer")
    return graph.compile(checkpointer=checkpointer)


_GRAPH = None
_STATEFUL_GRAPH = None


def get_graph(checkpointer: Any = None):
    global _GRAPH, _STATEFUL_GRAPH
    if checkpointer is not None:
        if _STATEFUL_GRAPH is None:
            _STATEFUL_GRAPH = _build_graph(checkpointer=checkpointer)
        return _STATEFUL_GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


async def stream_answer(
    question: str,
    context: str,
    history: List[Dict[str, str]] | None = None,
    thread_id: str | None = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Yield token, tool-status and usage events as the LangGraph run streams."""
    history = history or []
    messages: List[BaseMessage] = []
    for item in history[-10:]:
        role = item.get("role")
        content = item.get("content", "")
        if not content:
            continue
        messages.append(AIMessage(content=content) if role == "assistant" else HumanMessage(content=content))
    messages.append(HumanMessage(content=question))

    use_checkpointer = bool(thread_id and not history)
    if use_checkpointer:
        graph = get_graph(checkpointer=_CHECKPOINTER)
        config = {"configurable": {"thread_id": thread_id}}
    else:
        graph = get_graph()
        config = None

    tool_signaled = False
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    stream_kwargs: Dict[str, Any] = {
        "input": {"messages": messages, "context": context, "question": question},
        "stream_mode": "messages",
    }
    if config:
        stream_kwargs["config"] = config

    async for chunk, _meta in graph.astream(**stream_kwargs):
        if not isinstance(chunk, AIMessageChunk):
            continue
        for key, value in _extract_usage(chunk).items():
            usage_totals[key] += value

        tool_chunks = getattr(chunk, "tool_call_chunks", None)
        if tool_chunks and not tool_signaled:
            tool_signaled = True
            tool_name = ""
            for tool_chunk in tool_chunks:
                if isinstance(tool_chunk, dict) and tool_chunk.get("name"):
                    tool_name = str(tool_chunk.get("name"))
                    break
                if getattr(tool_chunk, "name", None):
                    tool_name = str(tool_chunk.name)
                    break
            labels = {
                "run_analysis": "正在运行经营深度分析…",
                "fetch_pospal_data": "正在拉取经营数据…",
                "query_product_sales": "正在查询单品销售明细…",
            }
            yield {
                "status": "tool",
                "label": labels.get(tool_name, "正在查询经营数据…"),
                "tool": tool_name,
            }
            continue

        content = chunk.content
        if content:
            if tool_signaled:
                tool_signaled = False
            yield {"token": content}

    if any(usage_totals.values()):
        yield {"usage": _usage_summary(usage_totals)}
