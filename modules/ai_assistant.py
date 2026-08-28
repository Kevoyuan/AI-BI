"""LangGraph-based AI assistant for the Web Dashboard (L1 insight narrator).

Design
------
* The frontend already holds the full dashboard JSON (``state.payload``). It
  POSTs that payload plus the user question and short chat history to
  ``/api/ai/chat``.
* This module compresses the payload into a compact business snapshot and feeds
  it as the system context to a DeepSeek (OpenAI-compatible) chat model.
* A LangGraph ``StateGraph`` runs a native tool-calling loop:
    START -> answer -> (tools_condition) -> tools -> answer -> ... -> END
  The model decides by itself whether to call the ``fetch_pospal_data`` tool,
  which wraps the existing ``get_dashboard_payload`` (银豹 live data + 4-level
  cache). This replaces the old Streamlit ``exec(code)`` data path.
* Answers stream token-by-token through LangGraph's ``stream_mode="messages"``
  so the server can push an SSE feed to the browser.

Only the LLM call and (optionally) the PosPal fetch touch the network.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Annotated, Any, AsyncGenerator, Dict, List, Sequence, TypedDict

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
    from langgraph.graph import END, START, StateGraph
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
  → 明天/下周销售额预测（近 4 周同星期加权 / 近 8 周趋势）。店主问"明天卖多少/备多少货"时用。
  预测是参考值，回答时用"预计/大约"措辞并给出置信区间，不要把预测当保证。
- 天气影响：run_analysis(analysis="weather", date_spec=...) → 各天气对销售的量化影响
  （以晴天为基准的系数%）+ 恶劣天气预警。店主问"下雨天影响大吗/今天要不要备外卖"时用。
- 购物篮连带：run_analysis(analysis="basket", date_spec=..., target_product="...") →
  全店平均连带率、多件单占比、TOP 共购商品搭配（置信度/提升度 Lift）。店主问"怎么提升客单价/某商品通常和什么一起买/怎么搭配套餐"时用。
- 时段客流潮汐：run_analysis(analysis="hourly", date_spec=...) →
  07:00~22:00 各小时营收、订单量(TC)、客单价(AC)及早/中/晚波峰占比。店主问"几点人最多/营业高峰/排班/几点主推什么"时用。
- 商品ABC与滞销诊断：run_analysis(analysis="abc", date_spec=...) →
  A类核心爆款(前70%)、B类腰部主力(20%)、C类长尾(10%)及滞销淘汰候选商品。店主问"哪些卖得最好/哪些商品该下架/结构如何"时用。
- 储值健康度：run_analysis(analysis="recharge", date_spec=...) →
  营收中直接现金进账 vs 储值卡消耗比例、新增充值金额与档位分布。店主问"储值情况怎么样/现金流健康吗/充值多不多"时用。
- date_spec 与 fetch_pospal_data 相同；结果可直接转成 chart spec 出图。

【工具调用行为规范】
1. 需要调用工具时，**直接发起工具调用，严禁在发出工具调用时输出任何占位或过渡文本**（例如严禁输出“我来拉取...”、“正在查询...”）。
2. 工具返回数据后，必须立刻基于拉取到的真实数据给出完整、详实的深度经营诊断与行动建议，严禁中途草率中断。

【可视化与富工件（Artifacts）渲染支持】
前端已原生支持多种精美的经营分析工件，适时使用可极大提升店主阅读体验：
1. 交互图表 (```chart 或 ```echarts)：
   - type 支持 line(折线) / bar(柱状) / hbar(横向条形) / pie(环形占比) / gauge(目标达成仪表盘) / scatter(散点)；
   - 示例: ```chart\n{"type":"gauge","title":"本月目标完成度","value":78.5,"unit":"%"}\n```
   - 示例: ```chart\n{"type":"bar","title":"本周各品类实收","labels":["现烤","西点","饮品"],"series":[{"name":"实收","values":[12000,8500,3200]}]}\n```
   - 特殊/高级需求（散点、热力图、双轴等）可改用 fenced 块 "```echarts" 直接给 ECharts option（纯 JSON 数据，禁止函数）。
2. 核心指标卡组 (```metrics)：
   - 快速展示 2~4 个关键 KPI，带涨跌幅徽章；
   - 示例: ```metrics\n[{"label":"本周实收","value":"¥3.2万","change":"+14.2%","trend":"up","note":"创近四周新高"},{"label":"综合报损率","value":"2.1%","change":"-0.8%","trend":"down","note":"处于安全线内"}]\n```
3. 方案对比卡 (```compare)：
   - 优化前 vs 优化后对比；
   - 示例: ```compare\n{"title":"清货方案对比","left":{"title":"现状 (打烊报废)","items":["报损率: 4.8%","损失: ¥650/天"]},"right":{"title":"建议 (20点盲盒打折)","items":["报损率降至: 1.2%","回收现金: +¥420/天"]}}\n```
4. 经营行动清单 (```checklist 或 Markdown 交互复选框 - [ ])：
   - 示例: ```checklist\n[{"task":"周六推出 38 元家庭下午茶套餐","priority":"high","impact":"+¥4,500"},{"task":"下调法式长棍每日产量 15%","priority":"medium","impact":"减损¥300"}]\n```
   - 或直接用 Markdown: `- [ ] 周六执行家庭套餐`
5. 提示/预警呼出框 (GitHub Alert 语法或 ```callout)：
   - 示例: `> [!WARNING]\n> 现烤类报损已达 6.2%，主要集中在 21:00 后未售出的牛角包。`
6. 结构化数据表 (Markdown Table)：
   - 多维度商品、分类明细必须使用标准 Markdown 管道表格 `| 商品 | 实收 | 报损 |`。

{context}

{domain}
"""


# 经营领域知识：从 skills/*/SKILL.md 提炼的"仍有效"判断知识（已过滤过时的
# 硬编码财务参数/目标值——那些以 monthly DB 的 financial 表为准）。
DOMAIN_KNOWLEDGE = """【经营领域知识（判断参考，勿当绝对真理）】
- 术语口径：TC=来客数（流水号去重）；AC=客单价（实收金额/TC）；报废率=报损金额/实收金额；
  试吃=备注或报损原因含「试吃」的项目，不计入经营报废；
  连带率=单据平均商品件数；多件单占比=购买件数>1的单据比例；净利润=实收金额-原料成本-运营管理-固定支出。
- 参考阈值（判断异常时使用）：
  · 连带率 <1.4 提示需加强组合推荐/收银加购；>1.8 表现优异
  · 储值卡消耗占比 >50% 且当期新充值低时，提示真实现金流承压风险
  · 报损率 >5% 值得预警；>8% 警告
  · 客单价波动 >15% 关注
  · 单日销售额低于近期均值 2 个标准差 → 高危异常
  · 连续 ≥5 天下滑 → 高危
  · 实际偏离目标 >20% → 警告
- 解读要点：
  · 面包店周节律明显：工作日平、周末高（周六/周日通常是周一~四的 1.5~2 倍）
  · 时段潮汐特征：早餐高峰(07:30-09:00, 吐司/咖啡主导)、午后茶歇(12:30-14:30, 甜包/饮品)、晚高峰(17:30-19:30, 现烤/家庭装)
  · 商品汰换建议：C类长尾商品若连续销量极低，建议果断下架以释放烤箱产能与展示台位
  · 恶劣天气（雨/台风）通常外卖占比升高、到店下降
  · 客单价提升抓手：高频共购组合打包（套餐价比单买优惠¥2~3）、收银台小单品（果酱/挂耳）加价购"""


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
class AIState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    context: str
    question: str


# --------------------------------------------------------------------------- #
# Context assembly (from dashboard payload)
# --------------------------------------------------------------------------- #
def _fmt_money(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        if abs(v) >= 10000:
            return f"¥{v/10000:.2f}万"
        if abs(v) >= 100:
            return f"¥{v:,.0f}"
        return f"{v:g}"
    return str(v)


def _fmt_pct(v: Any) -> str:
    try:
        return f"{float(v)*100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def build_context_from_payload(payload: Dict[str, Any] | None) -> str:
    """将看板 JSON 压缩为给 LLM 阅读的业务快照文本。"""
    if not payload:
        return "（暂无看板数据，请先加载经营数据）"

    parts: List[str] = []
    meta = payload.get("meta") or {}
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
        line = "，".join(f"{k}={_fmt_money(v)}" for k, v in items if v is not None)
        parts.append(f"### 核心 KPI：{line}")

    alerts = payload.get("alerts") or []
    if alerts:
        al = "；".join(f"[{a.get('level', '')}]{a.get('title', '')}" for a in alerts[:6])
        parts.append(f"### 业务提醒：{al}")

    tp = payload.get("topProducts") or []
    if tp:
        top = "，".join(f"{p.get('name')}({_fmt_money(p.get('amount'))})" for p in tp[:8])
        parts.append(f"### 热销商品 TOP：{top}")

    cm = payload.get("categoryMargin") or []
    if cm:
        cat = "，".join(
            f"{c.get('category')}(毛利率{_fmt_pct(c.get('margin'))})" for c in cm[:6]
        )
        parts.append(f"### 分类毛利：{cat}")

    wp = payload.get("weekdayPattern") or []
    if wp:
        wk = "，".join(f"{w.get('weekday')}:{_fmt_money(w.get('revenue'))}" for w in wp[:7])
        parts.append(f"### 周节律(各星期营收)：{wk}")

    eff = payload.get("efficiency") or {}
    if eff:
        try:
            eff_line = "，".join(f"{k}={_fmt_money(v)}" for k, v in eff.items() if v is not None)
            if eff_line:
                parts.append(f"### 经营效率：{eff_line}")
        except Exception:
            pass

    sm = payload.get("slowMovers") or []
    if sm:
        slow = "，".join(f"{s.get('name')}" for s in sm[:5])
        parts.append(f"### 滞销商品：{slow}")

    return "\n".join(parts)


def _build_system_prompt(context: str) -> str:
    # NOTE: use replace(), not .format() — the template contains JSON examples
    # with literal { } braces that .format() would try to parse as fields.
    return SYSTEM_TEMPLATE.replace("{context}", context).replace(
        "{domain}", DOMAIN_KNOWLEDGE
    )


# --------------------------------------------------------------------------- #
# PosPal data tool (replaces the old exec(code) data path)
# --------------------------------------------------------------------------- #
def _parse_date_spec(spec: Any) -> Any:
    from datetime import date
    import re
    from modules.dashboard_api import DashboardQuery

    if isinstance(spec, str):
        s = spec.strip()
        if s in ("today", "yesterday", "week", "month"):
            return DashboardQuery.from_preset(s)
        # Match YYYY-MM
        m = re.match(r"^(\d{4})[-/年](\d{1,2})月?$", s)
        if m:
            return DashboardQuery(year=int(m.group(1)), month=int(m.group(2)))
        # Match MM月
        m = re.match(r"^(\d{1,2})月$", s)
        if m:
            return DashboardQuery(year=2026, month=int(m.group(1)))
        # Match YYYY-MM-DD to YYYY-MM-DD
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*(?:[~至到,]|to)\s*(\d{4}-\d{2}-\d{2})$", s)
        if m:
            df, dt = m.group(1), m.group(2)
            start = date.fromisoformat(df)
            return DashboardQuery(year=start.year, month=start.month, date_from=df, date_to=dt)
        # Match single YYYY-MM-DD
        m = re.match(r"^(\d{4}-\d{2}-\d{2})$", s)
        if m:
            d = m.group(1)
            start = date.fromisoformat(d)
            return DashboardQuery(year=start.year, month=start.month, date_from=d, date_to=d)
        return DashboardQuery.current()

    if isinstance(spec, dict):
        if "preset" in spec:
            return DashboardQuery.from_preset(str(spec["preset"]))
        if "year" in spec and "month" in spec:
            return DashboardQuery(year=int(spec["year"]), month=int(spec["month"]))
        if "date_from" in spec and "date_to" in spec:
            df, dt = spec["date_from"], spec["date_to"]
            start = date.fromisoformat(df)
            return DashboardQuery(year=start.year, month=start.month, date_from=df, date_to=dt)

    return DashboardQuery.current()


@tool
def fetch_pospal_data(
    date_spec: Any,
    scope: str = "digest",
    refresh: bool = False,
    archive: bool = False,
) -> dict:
    """拉取银豹(PosPal)经营后台的实时/历史数据。

    Args:
        date_spec: 时间范围，支持以下任意形式：
            - 字典：{"preset": "month"} 或 {"year": 2026, "month": 6} 或 {"date_from": "2026-06-01", "date_to": "2026-06-30"}
            - 字符串："2026-06"、"2026-07"、"6月"、"month"、"2026-06-01~2026-08-20"
        scope: 返回粒度，控制 token 用量：
            - "digest"（默认）：预压缩**文本**快照（最省 token，普通问答首选）
            - "chart"：画图用的精简数组（限长，去大段）
            - "summary"：关键段原始 JSON（兼容旧用法）
            - "full"：全部聚合段（很大，谨慎）
            - "raw"：底层原始样本行（很大，仅追明细时用）
        refresh: 是否绕过缓存强制重新拉取（默认 False，优先用缓存；仍有 6 小时配额保护）。
        archive: 是否把涉及的月份标记为长期归档（永不因 TTL 过期而重新下载）。
                 适合老板要长期对比的历史月份；数据修正可之后用 refresh=True 覆盖。

    Returns:
        结构化数据字典（已按 scope 裁剪）。
    """
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
    """All (year, month) pairs covered by a DashboardQuery."""
    from datetime import date

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
    """按 scope 裁剪聚合结果，控制返回体积（也控制喂给 LLM 的 token）。

    - digest（默认）：预压缩**文本**快照（build_context_from_payload），token 最小
    - chart：画图用的精简数组（限长，去掉 weatherDaily 等大段）
    - summary：关键段原始 JSON（兼容）
    - full / raw：全量 / 原始样本行（谨慎使用，token 很大）
    """
    if scope == "full":
        return payload
    if scope == "raw":
        return {
            "meta": payload.get("meta", {}),
            "raw": payload.get("raw", payload),
        }
    if scope == "digest":
        return {
            "meta": payload.get("meta", {}),
            "digest": build_context_from_payload(payload),
        }
    if scope == "chart":
        out: Dict[str, Any] = {"meta": payload.get("meta", {})}
        kpis = payload.get("kpis")
        if kpis:
            out["kpis"] = kpis
        for key, limit in (
            ("daily", 60), ("hourly", 24), ("productABC", 30), ("slowMovers", 15),
            ("paymentMix", 10), ("weekdayPattern", 7), ("categoryMargin", 10),
            ("topProducts", 15), ("alerts", 10), ("kpiDeltas", 10),
        ):
            value = payload.get(key)
            if isinstance(value, list):
                out[key] = value[:limit]
            elif value is not None:
                out[key] = value
        return out
    summary_keys = [
        "meta", "kpis", "alerts", "daily", "topProducts", "productABC",
        "slowMovers", "paymentMix", "categoryMargin", "weekdayPattern",
        "weatherDaily", "memberSummary", "efficiency",
    ]
    return {k: payload[k] for k in summary_keys if k in payload}


@tool
def run_analysis(
    analysis: str,
    date_spec: Any = None,
    horizon: str = "tomorrow",
    target_product: str | None = None,
    top_n: int = 10,
) -> dict:
    """运行参数化经营分析（预测/天气影响/购物篮连带/时段客流/商品ABC/储值健康），返回结构化结果供回答或出图。

    Args:
        analysis: "forecast"(销售预测) | "weather"(天气影响) | "basket"(购物篮连带分析) | "hourly"(24小时时段客流画像) | "abc"(商品ABC与滞销诊断) | "recharge"(储值健康度)。
        date_spec: 时间范围，与 fetch_pospal_data 相同（preset / year+month /
            date_from~date_to；缺省近 30~45 天，最长 90 天）。支持字符串如 "2026-08" 或字典。
        horizon: forecast 专用："tomorrow"(预测明天) 或 "next_week"(预测下周)。
        target_product: basket 专用：指定某特定商品名称（如"生吐司"），查询与其最常共购的搭配。
        top_n: basket 专用：返回关联商品搭配对的数量（默认 10）。

    Returns:
        结构化分析结果字典。
    """
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
        if analysis == "recharge":
            return run_recharge_health(date_spec)
    except Exception as exc:
        logger.warning("分析工具 %s 执行异常: %s", analysis, exc)
        return {"analysis": analysis, "error": f"分析执行异常: {exc}"}


TOOLS = [fetch_pospal_data, run_analysis]


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #
def _build_llm() -> "ChatOpenAI":
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，AI 助手不可用")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    timeout = max(1.0, _env_float("DEEPSEEK_TIMEOUT_SECONDS", 60.0))
    max_retries = max(0, int(_env_float("DEEPSEEK_MAX_RETRIES", 2.0)))
    # DeepSeek's tool-calling is exposed via the OpenAI-compatible chat endpoint;
    # bind_tools attaches the JSON schema and lets the model emit tool_calls.
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
        temperature=0.3,
        max_tokens=1500,
        timeout=timeout,
        max_retries=max_retries,
    )


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return value if math.isfinite(value) and value >= 0 else default
    except (TypeError, ValueError):
        return default


def _extract_usage(chunk: AIMessageChunk) -> Dict[str, int]:
    """Normalize usage fields across LangChain/OpenAI-compatible responses."""
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
    """Return a stable, frontend-friendly token/cost ledger event."""
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    input_tokens = max(0, int(usage.get("input_tokens", 0)))
    output_tokens = max(0, int(usage.get("output_tokens", 0)))
    cached_tokens = min(
        input_tokens, max(0, int(usage.get("cached_input_tokens", 0)))
    )
    uncached_tokens = max(0, input_tokens - cached_tokens)

    # Prices are deliberately configurable: model pricing changes independently
    # of the portfolio app. The exact rates used for an event are sent along
    # with it so a ledger remains auditable after a future price change.
    input_rate = _env_float("DEEPSEEK_INPUT_USD_PER_MILLION", 0.28)
    cached_rate = _env_float("DEEPSEEK_CACHED_INPUT_USD_PER_MILLION", 0.028)
    output_rate = _env_float("DEEPSEEK_OUTPUT_USD_PER_MILLION", 0.42)
    input_cost = (
        uncached_tokens * input_rate + cached_tokens * cached_rate
    ) / 1_000_000
    uncached_cost = (input_tokens * input_rate) / 1_000_000
    output_cost = (output_tokens * output_rate) / 1_000_000
    return {
        "model": model,
        "inputTokens": input_tokens,
        "cachedInputTokens": cached_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
        "cacheHit": cached_tokens > 0,
        "costUsd": round(input_cost + output_cost, 8),
        "cacheSavingsUsd": round(max(0.0, uncached_cost - input_cost), 8),
        "priceVersion": os.getenv("DEEPSEEK_PRICE_VERSION", "env-configured"),
        "ratesUsdPerMillion": {
            "input": input_rate,
            "cachedInput": cached_rate,
            "output": output_rate,
        },
    }


# --------------------------------------------------------------------------- #
# Graph nodes
# --------------------------------------------------------------------------- #
async def _answer_node(state: AIState) -> Dict[str, Any]:
    llm = _build_llm().bind_tools(TOOLS)
    system = _build_system_prompt(state["context"])
    messages: List[BaseMessage] = [SystemMessage(content=system)]
    messages.extend(state["messages"])
    # ainvoke lets LangGraph's stream_mode="messages" intercept and emit
    # AIMessageChunk tokens (and tool_call chunks) to the caller.
    response = await llm.ainvoke(messages)
    return {"messages": [response]}


_CHECKPOINTER = MemorySaver()


def _build_graph(checkpointer: Any = None):
    g = StateGraph(AIState)
    g.add_node("answer", _answer_node)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "answer")
    g.add_conditional_edges("answer", tools_condition)
    g.add_edge("tools", "answer")
    return g.compile(checkpointer=checkpointer)


_GRAPH = None
_STATEFUL_GRAPH = None


def get_graph(checkpointer: Any = None):
    """获取编译后的图。若指定 checkpointer 则返回带状态持久化的图实例。"""
    global _GRAPH, _STATEFUL_GRAPH
    if checkpointer is not None:
        if _STATEFUL_GRAPH is None:
            _STATEFUL_GRAPH = _build_graph(checkpointer=checkpointer)
        return _STATEFUL_GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# --------------------------------------------------------------------------- #
# Public streaming entry point
# --------------------------------------------------------------------------- #
async def stream_answer(
    question: str,
    context: str,
    history: List[Dict[str, str]] | None = None,
    thread_id: str | None = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Yield ``{"token": ...}`` / ``{"status": ...}`` dicts as they arrive.

    ``history`` is a list of ``{"role": "user"|"assistant", "content": "..."}``.
    ``thread_id`` can optionally identify a continuous multi-turn session in Checkpointer.
    """
    history = history or []
    messages: List[BaseMessage] = []
    for h in history[-10:]:
        role = h.get("role")
        content = h.get("content", "")
        if not content:
            continue
        messages.append(
            AIMessage(content=content)
            if role == "assistant"
            else HumanMessage(content=content)
        )
    messages.append(HumanMessage(content=question))

    # Browser-persisted sessions send their complete history explicitly. In
    # that mode a checkpointer would append the same messages a second time,
    # causing duplicated prompts and unbounded context growth. Checkpointer
    # remains available for server-owned callers that omit history entirely.
    use_checkpointer = bool(thread_id and not history)
    if use_checkpointer:
        graph = get_graph(checkpointer=_CHECKPOINTER)
        config = {"configurable": {"thread_id": thread_id}}
    else:
        graph = get_graph()
        config = None

    tool_signaled = False
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    astream_kwargs: Dict[str, Any] = {
        "input": {"messages": messages, "context": context, "question": question},
        "stream_mode": "messages",
    }
    if config:
        astream_kwargs["config"] = config

    async for chunk, _meta in graph.astream(**astream_kwargs):
        if not isinstance(chunk, AIMessageChunk):
            continue
        chunk_usage = _extract_usage(chunk)
        for key, value in chunk_usage.items():
            usage_totals[key] += value
        # The model requested a tool call — surface a "querying" status once.
        if getattr(chunk, "tool_call_chunks", None) and not tool_signaled:
            tool_signaled = True
            yield {"status": "tool", "label": "正在查询经营数据…"}
            continue
        content = chunk.content
        if content:
            if tool_signaled:
                tool_signaled = False  # reset so a 2nd tool round (if any) re-signals
            yield {"token": content}
    if any(usage_totals.values()):
        yield {"usage": _usage_summary(usage_totals)}
