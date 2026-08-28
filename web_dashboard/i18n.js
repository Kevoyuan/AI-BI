/** Lightweight bilingual UI layer for the no-build dashboard. */
(() => {
  const win = window;
  const doc = document;
  const storageKey = "ai-bi.language";
  const pairs = {
    "经营 API 仪表盘": "Operations API Dashboard",
    "经营": "Business",
    "API 仪表盘": "API Dashboard",
    "API 仪表盘": "API Dashboard",
    "数据直连银豹后台接口 · 不写入本地数据库": "Direct PosPal API data · no local database writes",
    "银豹 POS 实收、报损与储值卡月度回看 · 净利润根据财务参数动态估算": "Monthly PosPal POS review of net revenue, waste, and stored-value cards · estimated net profit uses the configured finance parameters",
    "时间范围": "Time range",
    "今日": "Today",
    "昨日": "Yesterday",
    "本周": "This week",
    "本月": "This month",
    "年份": "Year",
    "月份": "Month",
    "开始日期": "Start date",
    "结束日期": "End date",
    "刷新接口数据": "Refresh API data",
    "等待加载": "Waiting to load",
    "从银豹后台接口读取数据。": "Reading data from the PosPal API.",
    "正在从银豹后台接口读取数据。": "Reading data from the PosPal API…",
    "门店经营": "Store performance",
    "快照": "Snapshot",
    "数据更新于": "Updated",
    "刷新数据": "Refresh data",
    "下载 JSON ↓": "Download JSON ↓",
    "业务提醒": "Business alerts",
    "仪表盘视图": "Dashboard views",
    "AI 经营助手": "AI Business Assistant",
    "经营概览": "Overview",
    "收入分类": "Revenue",
    "商品分析": "Products",
    "报损与储值": "Waste & Stored Value",
    "业务洞察": "Insights",
    "天气 × 实收": "Weather × Revenue",
    "天气记录": "Weather Log",
    "明细": "Details",
    "AI 智能经营顾问": "AI Business Advisor",
    "历史对话": "Conversation history",
    "新建对话": "New conversation",
    "清空对话": "Clear conversation",
    "基于当前看板经营数据实时分析": "Real-time analysis of the current dashboard",
    "基于当前看板数据回答": "Answers based on current dashboard data",
    "基于": "Based on",
    "数据回答": " data",
    "银豹后台接口": "PosPal API",
    "先加载经营数据以获得更准的回答": "Load business data for a more accurate answer",
    "您好，我是您的专属烘焙经营助手": "Hello, I’m your dedicated bakery business assistant",
    "营收提升与提单": "Revenue & basket growth",
    "控损与滞销诊断": "Waste & slow-mover diagnosis",
    "选品与毛利结构": "Product mix & margin",
    "天气与智能备货": "Weather & smart stocking",
    "银豹整体概况": "PosPal Overview",
    "每日走势": "Daily Trend",
    "营业时段与日内节奏": "Trading Hours & Daily Rhythm",
    "月度日历": "Monthly Calendar",
    "优惠与折让": "Discounts & Adjustments",
    "收款结构": "Payment Mix",
    "会员与储值": "Members & Stored Value",
    "小时销售热度": "Hourly Sales Heat",
    "时段排产与陈列策略": "Dayparting & Merchandising",
    "每日汇总": "Daily Summary",
    "收入分类明细": "Revenue Category Detail",
    "来源": "Channels",
    "商品销售 Top 30": "Top 30 Products",
    "商品利润 Top 10 / Bottom 5": "Top 10 / Bottom 5 Product Profit",
    "商品选品与毛利四象限": "Product Mix & Margin Matrix",
    "销售明细": "Sales Detail",
    "暂无数据": "No data available",
    "本月无报废数据": "No waste data this month",
    "暂无订单时段": "No hourly orders",
    "少": "Low",
    "多": "High",
    "商品": "Product",
    "商品分类": "Product category",
    "数量": "Quantity",
    "订单": "Orders",
    "实收": "Net revenue",
    "实收金额": "Net revenue",
    "订单数": "Orders",
    "客单价": "Average ticket",
    "净利润": "Net profit",
    "净利润估算": "Estimated net profit",
    "商品总价累计": "Cumulative list price",
    "实收金额累计": "Cumulative net revenue",
    "订单笔数累计": "Cumulative orders",
    "损耗价值累计": "Cumulative waste value",
    "净利润累计": "Cumulative net profit",
    "总净利润率": "Overall net margin",
    "累计净利润": "Cumulative net profit",
    "金额": "Amount",
    "占比": "Share",
    "来源分布": "Channel mix",
    "损耗价值": "Waste value",
    "充值总金额": "Total recharge",
    "储值卡消费": "Stored-value spending",
    "高损预警": "High-waste alert",
    "偏高": "Elevated",
    "健康": "Healthy",
    "日均利润": "Daily profit",
    "日均": "Daily avg.",
    "单": "orders",
    "连带": "Basket",
    "件/单": "items/order",
    "件均": "Avg. item",
    "客均消费": "Avg. spend",
    "综合报损率": "Overall waste rate",
    "报损": "Waste",
    "储值充值": "Stored-value recharge",
    "会员资金池沉淀": "Member funds retained",
    "报损金额": "Waste amount",
    "储值卡充值": "Stored-value recharge",
    "充值金额": "Recharge amount",
    "会员手机号": "Member phone",
    "会员卡号": "Member card",
    "报损率": "Waste rate",
    "毛利率": "Gross margin",
    "累计": "Cumulative",
    "营业额": "Revenue",
    "高峰时段": "Peak hours",
    "时段": "period",
    "营业实收": "Net revenue",
    "订单笔数": "Order count",
    "平均客单价": "Average ticket",
    "时段订单数": "Orders in period",
    "实收": "Revenue",
    "单数": "Orders",
    "对比": "Compare",
    "工作日": "Weekdays",
    "周末": "Weekend",
    "早市": "Morning",
    "午市": "Midday",
    "下午": "Afternoon",
    "晚市": "Evening",
    "加载失败": "Load failed",
    "接口已同步": "API synced",
    "正在加载": "Loading",
    "额度保护刷新完成": "Quota-protected refresh complete",
    "提示": "Note",
    "建议": "Suggestion",
    "重要": "Important",
    "预警": "Warning",
    "注意": "Caution",
    "正在渲染组件…": "Rendering component…",
    "复制": "Copy",
    "已复制": "Copied",
    "正在查询数据…": "Querying data…",
    "重试本次提问": "Retry this question",
    "本会话成本": "Session cost",
    "tokens": "tokens",
    "缓存节省": "Cache savings",
    "正在思考，通常需要几秒…": "Thinking, this usually takes a few seconds…",
    "连接稍慢，正在重试（2/2）…": "The connection is slow, retrying (2/2)…",
    "按免费额度保护策略刷新；当前月最多每 6 小时重新拉取一次": "Refresh under quota protection; the current month is fetched at most every 6 hours",
    "唤起 AI 经营助手": "Open the AI business assistant",
    "发送": "Send",
    "历史对话列表": "Conversation history list",
    "输入您的经营问题，如：分析这3个月的滞销品（按 Enter 发送，Shift+Enter 换行）…": "Ask a business question, e.g. analyze slow movers from the last 3 months (Enter to send, Shift+Enter for a new line)…",
    "您好，我是您的专属烘焙经营助手": "Hello, I’m your dedicated bakery business assistant",
    "已接入银豹后台实时接口与天气对齐模型，可随时为您诊断异常、推演备货并制定增收策略。": "Connected to the PosPal API and weather alignment model for anomaly diagnosis, stocking forecasts, and revenue strategies.",
    "这周报损率是不是偏高？": "Is this week’s waste rate too high?",
    "周二销量为什么低？": "Why were Tuesday sales low?",
    "给我 3 条本周提升营收的建议": "Give me 3 ways to increase revenue this week",
    "这3个月的滞销品分析一下": "Analyze slow movers from the last 3 months",
    "明天预计备多少货？": "How much should we stock tomorrow?",
    "经营简报与决策导向": "Business brief & decision guidance",
    "营收与产出节奏": "Revenue & production rhythm",
    "控损与健康度": "Waste control & health",
    "选品与优化建议": "Product mix & optimization",
    "查看波士顿四象限与淘汰建议 →": "View the BCG matrix and removal recommendations →",
  };
  const reverse = Object.fromEntries(Object.entries(pairs).map(([zh, en]) => [en, zh]));
  let language = "zh";

  try {
    const saved = win.localStorage.getItem(storageKey);
    if (saved === "en" || saved === "zh") language = saved;
  } catch (_) {}

  function translate(value) {
    const text = String(value);
    const trimmed = text.trim();
    const normalized = trimmed.replace(/\s+/g, " ");
    const translated = language === "en" ? (pairs[trimmed] || pairs[normalized]) : (reverse[trimmed] || reverse[normalized]);
    if (!translated) return text;
    return text === trimmed ? translated : text.replace(trimmed, translated);
  }

  function translatePage(root = doc) {
    if (!root) return;
    const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (parent && !["SCRIPT", "STYLE"].includes(parent.tagName)) nodes.push(node);
    }
    nodes.forEach((textNode) => {
      const next = translate(textNode.nodeValue);
      if (next !== textNode.nodeValue) textNode.nodeValue = next;
    });
    root.querySelectorAll?.("[title], [aria-label], [placeholder]").forEach((element) => {
      ["title", "aria-label", "placeholder"].forEach((attribute) => {
        if (element.hasAttribute(attribute)) {
          const next = translate(element.getAttribute(attribute));
          if (next !== element.getAttribute(attribute)) element.setAttribute(attribute, next);
        }
      });
    });
  }

  function updateToggle() {
    doc.documentElement.lang = language === "en" ? "en" : "zh-CN";
    const toggle = doc.getElementById("language-toggle");
    if (!toggle) return;
    toggle.querySelectorAll("[data-lang]").forEach((button) => {
      const active = button.dataset.lang === language;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function setLanguage(next) {
    if (next !== "en" && next !== "zh") return;
    language = next;
    try { win.localStorage.setItem(storageKey, language); } catch (_) {}
    updateToggle();
    translatePage(doc.body);
    win.dispatchEvent(new CustomEvent("languagechange", { detail: { language } }));
  }

  win.I18n = {
    get language() { return language; },
    t: translate,
    setLanguage,
    translatePage,
  };

  doc.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-lang]");
    if (button) setLanguage(button.dataset.lang);
  });
  updateToggle();
  translatePage(doc.body);

  const observer = new MutationObserver((records) => {
    records.forEach((record) => {
      record.addedNodes.forEach((added) => {
        if (added.nodeType === Node.ELEMENT_NODE || added.nodeType === Node.TEXT_NODE) {
          translatePage(added.nodeType === Node.TEXT_NODE ? added.parentElement : added);
        }
      });
    });
  });
  observer.observe(doc.body, { childList: true, subtree: true });
})();
