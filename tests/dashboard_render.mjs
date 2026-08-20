// Render smoke test using Node's built-in vm + a thin DOM shim.
// We don't try to start the real fetch (no network) — we directly call
// the JS module's render() function with a synthetic mock payload, and
// assert that each output element got non-empty innerHTML.

import { readFileSync, writeFileSync } from "node:fs";
import vm from "node:vm";
import process from "node:process";

const js = readFileSync("web_dashboard/app.js", "utf8");
const html = readFileSync("web_dashboard/index.html", "utf8");

if (!html.includes('class="product-top-grid"') || html.includes('id="p-4-商品-top-30-明细"')) {
  console.error("Product Top 30 ranking and detail panels were not merged");
  process.exit(1);
}

// Synthetic test payload (only used inside this dev test, never served)
const mock = {
  meta: { year: 2025, month: 6, range: "2025-06-01 至 2025-06-15", generatedAt: "2025-06-07 21:30:00", source: "test" },
  kpis: { revenue: 184326, orders: 2840, avgTicket: 64.9, loss: 3120, cardRecharge: 12400, netProfit: 42500 },
  kpiDeltas: { revenue: { delta: 0.08, trend: "up" }, orders: { delta: 0.04, trend: "up" }, avgTicket: { delta: -0.01, trend: "flat" }, netProfit: { delta: 0.21, trend: "up" } },
  cumulative: { 商品总价累计: 92300, 实收金额累计: 184326, 订单笔数累计: 2840, 损耗价值累计: 3120, 净利润累计: 42500, 总净利润率: 23.05, series: [{日期: "2025-06-01", 净利润累计: 1000}, {日期: "2025-06-02", 净利润累计: 2500}] },
  daily: [{日期: "2025-06-01", 实收金额: 5500, 商品总价: 2100, 销售数量: 80, 订单笔数: 95, 损耗价值: 60, 报废数量: 2, 储值卡充值: 400, 储值卡消费: 200, 商品成本估算: 945, 固定支出: 800, 净利润估算: 3755, 客单价: 57.9, 报损率: 0.028}],
  hourly: [{小时: 12, 实收金额: 1000, 订单数: 30}],
  incomeCategories: [{收入分类: "烘焙", 实收金额: 100, 订单数: 10}],
  sources: [{来源: "门店", 实收金额: 100, 订单数: 5}],
  topProducts: [{商品名称: "可颂", 商品分类: "面包", 收入分类: "bakery", 实收金额: 100, 销售数量: 30, 订单数: 25}],
  lossReasons: [{报损原因: "过期", 报损金额: 100, 报废数量: 5}],
  cards: [{日期: "2025-06-01", 充值总金额: 400, 储值卡消费总金额: 200, 本金消费金额: 150, 赠送消费金额: 50}],
  recharge: [{支付分类: "微信", 充值金额: 400, 赠送金额: 50, 笔数: 10}],
  weekdayPattern: [{日期: "2025-06-01", 周几: 0, 实收金额: 5500, 订单数: 95}],
  weekendVsWeekday: {weekdayRevenue: 1000, weekendRevenue: 500, weekdayOrders: 50, weekendOrders: 20, weekdayDays: 10, weekendDays: 4},
  productABC: [{商品名称: "可颂", 实收金额: 100, 销售数量: 30, 累计占比: 0.5, ABC分类: "A"}],
  slowMovers: [{商品名称: "冷门", 商品分类: "其他", 实收金额: 10, 销售数量: 1, 订单数: 1}],
  lossDailyAnomaly: [{日期: "2025-06-01", 损耗价值: 60, 报损率: 0.028, 异常: false, 严重程度: "ok"}],
  categoryMargin: [{收入分类: "烘焙", 实收金额: 100, 商品总价: 30, 毛利: 70, 毛利率: 0.7}],
  cardNet: [{日期: "2025-06-01", 净值: 200, 累计余额: 200}],
  efficiency: {costRatio: 0.6, breakevenDays: 10, operatingDays: 15, profitMargin: 0.23, totalRevenue: 100000, totalCost: 60000},
  alerts: [{level: "warn", title: "测试告警", detail: "smoke test alert"}],
  orderHeatmap: [{日期: "2025-06-01", 小时: 9, 订单数: 0, 实收金额: 0}, {日期: "2025-06-01", 小时: 12, 订单数: 30, 实收金额: 100}],
  hourPeriod: {morning: {订单数: 10, 实收金额: 100, 占比: 0.3}, noon: {订单数: 20, 实收金额: 200, 占比: 0.5}, afternoon: {订单数: 5, 实收金额: 50, 占比: 0.1}, evening: {订单数: 5, 实收金额: 50, 占比: 0.1}, peak: {hour: 12, 订单数: 20}},
  highValueOrders: {高价值订单数: 5, 总订单数: 10, 高价值订单占比: 0.5, 平均订单金额: 60, 高价值平均金额: 100, buckets: [{区间: "50–100", 订单数: 5}]},
  ticketDistribution: [{小时: 12, 订单数: 30, 实收金额: 100, 客单价: 3.3}],
  lossByCategory: [{商品分类: "面包", 报损金额: 60, 报废数量: 2}],
  cardSummary: {充值总金额: 400, 储值卡消费: 200, 本金消费: 150, 赠送消费: 50},
  volatility: {days: 1, mean: 100, median: 100, std: 0, cv: 0, min: 100, max: 100, range: 0, iqr: 0, skewness: 0, bestDay: {date: "2025-06-01", value: 100}, worstDay: {date: "2025-06-01", value: 100}, percentiles: {P10: 100, P25: 100, P50: 100, P75: 100, P90: 100}},
  concentration: {total: 100, skus: 1, shares: [{q: 0.1, share: 0.1}, {q: 1.0, share: 1.0}], hhi: 1, top5Share: 1, top20Share: 1},
  categoryByHour: [{收入分类: "烘焙", 小时: 7, 实收金额: 80}, {收入分类: "烘焙", 小时: 9, 实收金额: 90}, {收入分类: "烘焙", 小时: 12, 实收金额: 100}],
  orderAmountDist: [{区间: "0–20", 订单数: 10, 占比: 0.5}],
  discounts: {销售金额: 100, 实收金额: 95, 优惠金额: 5, 优惠率: 0.05, 优惠单数: 5, 订单总数: 10, 优惠单占比: 0.5, dailyTrend: []},
  paymentMix: {
    total: 100,
    methodCount: 2,
    paymentCount: 3,
    orderCount: 2,
    mixedPaymentOrders: 1,
    averagePerOrder: 50,
    dominantMethod: "微信",
    dominantShare: 0.7,
    expectedRevenue: 100,
    reconciliationGap: 0,
    coverage: 1,
    reconciled: true,
    status: "available",
    methods: [
      {支付方式: "微信", 金额: 70, 占比: 0.7, 支付笔数: 2, 订单数: 2, 平均每单: 35},
      {支付方式: "现金", 金额: 30, 占比: 0.3, 支付笔数: 1, 订单数: 1, 平均每单: 30},
    ],
  },
  weatherDaily: {
    status: "available",
    message: "已获取虎门 2 天天气",
    provider: "Open-Meteo",
    location: "示范城市 · 示范区",
    latitude: 22.81899,
    longitude: 113.67306,
    fetchedAt: "2025-06-07 08:30:00",
    latest: {date: "2025-06-07", isToday: true, condition: "中雨", category: "中雨", icon: "🌧", temperatureMax: 31.2, temperatureMin: 24.1, temperatureMean: 27.5, precipitation: 18.2, rain: 17.8, precipitationHours: 5, sunshineHours: 3.5, windSpeedMax: 22.4, dataType: "近期/预报"},
    days: [
      {date: "2025-06-07", isToday: true, condition: "中雨", category: "中雨", icon: "🌧", temperatureMax: 31.2, temperatureMin: 24.1, temperatureMean: 27.5, precipitation: 18.2, rain: 17.8, precipitationHours: 5, sunshineHours: 3.5, windSpeedMax: 22.4, dataType: "近期/预报"},
      {date: "2025-06-06", isToday: false, condition: "晴", category: "晴朗", icon: "☀", temperatureMax: 33.4, temperatureMin: 25.1, temperatureMean: 29.1, precipitation: 0, rain: 0, precipitationHours: 0, sunshineHours: 10.2, windSpeedMax: 15.8, dataType: "历史再分析"},
    ],
  },
  weatherSales: {
    status: "available",
    summary: {
      totalDays: 2,
      rainDays: 1,
      dryDays: 1,
      rainAvgRevenue: 800,
      dryAvgRevenue: 1000,
      rainAvgOrders: 30,
      dryAvgOrders: 40,
      rainAvgTicket: 26.6,
      dryAvgTicket: 25.0,
      rainImpactPct: -20.0,
      bestCondition: {condition: "晴", icon: "☀", avgRevenue: 1000, days: 1, avgOrders: 40, avgTicket: 25, impactPct: 0},
      worstCondition: {condition: "中雨", icon: "🌧", avgRevenue: 800, days: 1},
    },
    byCondition: [
      {condition: "晴", icon: "☀", days: 1, totalRevenue: 1000, avgRevenue: 1000, avgOrders: 40, avgTicket: 25, impactPct: 0},
      {condition: "中雨", icon: "🌧", days: 1, totalRevenue: 800, avgRevenue: 800, avgOrders: 30, avgTicket: 26.6, impactPct: -20.0},
    ],
    timeline: [
      {date: "2025-06-06", condition: "晴", icon: "☀", revenue: 1000, orders: 40, ticket: 25, tempMax: 33.4, tempMin: 25.1, precipitation: 0},
      {date: "2025-06-07", condition: "中雨", icon: "🌧", revenue: 800, orders: 30, ticket: 26.6, tempMax: 31.2, tempMin: 24.1, precipitation: 18.2},
    ],
    scatter: [
      {date: "2025-06-06", condition: "晴", icon: "☀", revenue: 1000, orders: 40, ticket: 25, tempMax: 33.4, precipitation: 0},
      {date: "2025-06-07", condition: "中雨", icon: "🌧", revenue: 800, orders: 30, ticket: 26.6, tempMax: 31.2, precipitation: 18.2},
    ],
    table: [
      {日期: "2025-06-06", 天气: "☀ 晴", 最高温: 33.4, 最低温: 25.1, 降水量: 0, 实收金额: 1000, 订单数: 40, 客单价: 25},
      {日期: "2025-06-07", 天气: "🌧 中雨", 最高温: 31.2, 最低温: 24.1, 降水量: 18.2, 实收金额: 800, 订单数: 30, 客单价: 26.6},
    ],
  },
  ticketType: {total: 100, types: [{类型: "销售", 单数: 2, 实收金额: 100, 占比: 1}]},
  profitByProduct: [{商品名称: "可颂", 商品分类: "面包", 收入分类: "bakery", 实收金额: 100, 销售数量: 30, 订单数: 25, 利润: 40, 利润率: 0.4}],
  lossByReason: {reasons: [{报损原因: "过期", 报损金额: 100, 报废数量: 5}], totalAmount: 100, totalQuantity: 5},
  memberSummary: {会员数: 100, 剩余金额: 5000, 充值金额: 400, 赠送金额: 50},
  cardBalance: {本金消费: 150, 赠送消费: 50, 本金赠送比: 3},
  pospalOverview: {
    period: {selected: "month", options: ["today", "yesterday", "week", "month"], label: "2025-06"},
    business: {营业实收: 1806.2, 销售金额: 1806.2, 销售金额退: 0, 订单总数: 70, 堂食单数: 70, 外卖单数: 0, 其他单数: 0, 客单价: 25.8, 优惠金额: 34.8, 优惠单数: 14, 发券数量: 0, 券付单数: 0, 门店实收: 1806.2, 门店订单: 70},
    onlineStore: {网店实收: 0, 支付订单: 0, 访客数量: null, 新增会员: 0},
    hourlyTrend: [{小时: 10, 营业额: 50, 订单数: 2}, {小时: 11, 营业额: 80, 订单数: 3}, {小时: 12, 营业额: 160, 订单数: 6}],
    marketingCalendar: [{日期: "06-18", 名称: "618购物节", 剩余天数: 10, status: "upcoming"}],
    smsBalance: {余额条数: null, status: "unavailable", message: "当前导出接口未返回短信余额"},
  },
  openCloseHours: {openHour: 7, closeHour: 22, peakHour: 12, openAmount: 100, closeAmount: 200, ramp: 300, wind: 600, isOpen: true},
  calendar: [{日期: "2025-06-01", 实收金额: 100, 净利润: 50, 订单数: 30, 报损率: 0.02, 状态: "ok"}],
  raw: {sales: [], loss: [], cards: [], cardsDetail: [], salesDetail: []},
};

// --- DOM shim ---
function makeEl(tag = "div") {
  const node = {
    tagName: tag.toUpperCase(),
    children: [],
    childNodes: [],
    dataset: {},
    _html: "",
    _text: "",
    _attrs: {},
    _listeners: {},
    classList: makeClassList(),
    style: {},
    parentNode: null,
  };
  Object.defineProperty(node, "innerHTML", {
    get() { return this._html; },
    set(v) { this._html = String(v); },
    enumerable: true,
  });
  Object.defineProperty(node, "textContent", {
    get() { return this._text; },
    set(v) { this._text = String(v); },
    enumerable: true,
  });
  node.setAttribute = (k, v) => { node._attrs[k] = String(v); };
  node.getAttribute = (k) => node._attrs[k] ?? null;
  node.appendChild = (child) => { node.children.push(child); node.childNodes.push(child); child.parentNode = node; return child; };
  node.append = (...nodes) => { for (const n of nodes) node.appendChild(n); };
  node.addEventListener = (ev, fn) => { (node._listeners[ev] = node._listeners[ev] || []).push(fn); };
  node.querySelector = () => makeEl();
  node.querySelectorAll = () => [];
  node.click = function() { (this._listeners.click || []).forEach((fn) => fn({ preventDefault() {} })); };
  return node;
}

function makeClassList() {
  const set = new Set();
  return {
    _set: set,
    add(...c) { c.forEach((x) => set.add(x)); },
    remove(...c) { c.forEach((x) => set.delete(x)); },
    toggle(c, force) {
      if (force === true) set.add(c);
      else if (force === false) set.delete(c);
      else if (set.has(c)) set.delete(c);
      else set.add(c);
    },
    contains(c) { return set.has(c); },
  };
}

// Track all elements we hand out via querySelector
const elementsBySel = new Map();
function getOrCreate(sel) {
  if (!elementsBySel.has(sel)) elementsBySel.set(sel, makeEl());
  return elementsBySel.get(sel);
}

// Special: querySelectorAll(".tab") and (.tab-panel) and (.raw-tab)
const tabButtons = ["overview", "income", "product", "loss", "insight", "weather-sales", "weather", "raw"].map((t) => {
  const b = makeEl("button");
  b.dataset.tab = t;
  if (t === "overview") b.classList.add("active");
  return b;
});
const tabPanels = ["overview", "income", "product", "loss", "insight", "weather-sales", "weather", "raw"].map((t) => {
  const p = makeEl("section");
  p.dataset.panel = t;
  if (t === "overview") p.classList.add("active");
  return p;
});
const rawTabs = ["sales", "loss", "cards", "cardsDetail", "salesDetail"].map((t) => {
  const b = makeEl("button");
  b.dataset.raw = t;
  if (t === "sales") b.classList.add("active");
  return b;
});

// Stub document.body for the JS module's appendChild
const body = makeEl("body");
body.appendChild = () => {};

const document = {
  createElement: (tag) => makeEl(tag),
  createElementNS: (_ns, tag) => makeEl(tag),
  addEventListener: () => {},
  removeEventListener: () => {},
  body,
  querySelector(sel) {
    if (sel === ".tab") return tabButtons[0];
    if (sel.startsWith(".tab-")) return null;
    if (sel === ".raw-tab") return rawTabs[0];
    return getOrCreate(sel);
  },
  querySelectorAll(sel) {
    if (sel === ".tab") return tabButtons;
    if (sel === ".tab-panel") return tabPanels;
    if (sel === ".raw-tab") return rawTabs;
    return [];
  },
};

// Pre-register all the elements the JS will query
const SELS = [
  "#filters", "#year", "#month", "#loading", "#content", "#error",
  "#status-card", "#status-title", "#status-copy", "#range-label",
  "#updated-at", "#live-time", "#foot-stamp", "#kpis",
  "#daily-chart", "#daily-table", "#hour-chart",
  "#income-bars", "#income-table", "#source-donut", "#source-legend",
  "#product-bars", "#product-table", "#loss-list", "#card-chart",
  "#recharge-table", "#raw-table", "#raw-tabs",
  "#legend-daily", "#legend-card", "#download-json",
  "#cumulative", "#cum-chart",
  "#order-heatmap", "#hour-period", "#high-value", "#ticket-chart",
  "#loss-by-category", "#card-summary",
  "#alerts-banner", "#alerts-list", "#alerts-count",
  "#heatmap", "#weekday-bars", "#category-margin", "#efficiency",
  "#loss-anomaly", "#card-net-chart",
  "#abc-summary", "#abc-table", "#slow-table",
  "#weather-daily",
  "#weather-sales-summary", "#weather-sales-condition-chart",
  "#weather-sales-scatter-chart", "#weather-sales-timeline-chart",
  "#weather-sales-table",
];
for (const s of SELS) getOrCreate(s);

globalThis.Option = class Option {
  constructor(value, text, defaultSelected, selected) {
    this.value = String(value);
    this.text = String(text);
    this.defaultSelected = !!defaultSelected;
    this.selected = !!selected;
  }
};

const mockECharts = {
  init(dom) {
    return {
      setOption(opt) {
        dom.innerHTML = `<div class="mock-echarts" data-series="${(opt.series || []).length}">[ECharts Canvas]</div>`;
      },
      resize() {},
      dispose() {},
      isDisposed() { return false; },
    };
  },
  getInstanceByDom() {
    return null;
  },
  graphic: {
    LinearGradient: class {
      constructor() {}
    },
  },
};

// Build a sandbox context
const ctx = vm.createContext({
  document,
  window: { echarts: mockECharts, addEventListener: () => {}, removeEventListener: () => {} },
  echarts: mockECharts,
  Intl, Number, String, Math, JSON, Date, Array, Object, Set, Map, Promise,
  URLSearchParams, URL,
  Option: globalThis.Option,
  setInterval: () => 0,
  // Run the callback synchronously, but if it returns a Promise, swallow any
  // rejection (errors are surfaced via the test's mock fetch).
  setTimeout: (fn) => {
    try {
      const r = fn();
      if (r && typeof r.catch === "function") r.catch(() => {});
    } catch (_) { /* ignore synchronous throws in callbacks */ }
    return 0;
  },
  requestAnimationFrame: (cb) => cb(),
  console,
});
ctx.fetch = async () => ({
  ok: true,
  status: 200,
  json: async () => mock,
});

// Run the JS module
try {
  vm.runInContext(js, ctx);
} catch (e) {
  console.error("JS ERROR:", e.message);
  console.error(e.stack);
  process.exit(1);
}

// Give async chain time. init() is async, calls loadDashboard() which
// awaits fetch(). Use multiple Promise.resolve() to drain microtasks,
// then settle each macrotask via setImmediate. Repeat until render()
// actually populated the DOM, or we hit a generous limit.
for (let i = 0; i < 50; i += 1) {
  for (let j = 0; j < 5; j += 1) await Promise.resolve();
  await new Promise((r) => setImmediate(r));
  if (elementsBySel.get("#kpis")?._html || i === 49) break;
}

// Check that each render target got content
const checks = [
  ["#alerts-list", "alerts list"],
  ["#kpis", "KPI band"],
  ["#cumulative", "cumulative band"],
  ["#cum-chart", "cumulative chart"],
  ["#daily-chart", "daily chart"],
  ["#hour-chart", "hour chart"],
  ["#daily-table", "daily table"],
  ["#income-bars", "income bars"],
  ["#source-donut", "source donut"],
  ["#source-legend", "source legend"],
  ["#product-bars", "product bars"],
  ["#product-table", "product table"],
  ["#loss-list", "loss list"],
  ["#card-chart", "card chart"],
  ["#recharge-table", "recharge table"],
  ["#order-heatmap", "order heatmap"],
  ["#hour-period", "hour period"],
  ["#high-value", "high value"],
  ["#ticket-chart", "ticket chart"],
  ["#loss-by-category", "loss by category"],
  ["#card-summary", "card summary"],
  ["#heatmap", "weekday heatmap"],
  ["#weekday-bars", "weekday bars"],
  ["#category-margin", "category margin"],
  ["#efficiency", "efficiency"],
  ["#loss-anomaly", "loss anomaly"],
  ["#card-net-chart", "card net chart"],
  ["#abc-summary", "abc summary"],
  ["#abc-table", "abc table"],
  ["#slow-table", "slow table"],
  ["#volatility", "volatility"],
  ["#lorenz-stats", "lorenz stats"],
  ["#lorenz-chart", "lorenz chart"],
  ["#cat-hour-heat", "category hour heat"],
  ["#order-amount-dist", "order amount dist"],
  ["#weather-daily", "weather archive"],
  ["#weather-sales-summary", "weather sales summary"],
  ["#weather-sales-condition-chart", "weather sales condition chart"],
  ["#weather-sales-scatter-chart", "weather sales scatter chart"],
  ["#weather-sales-timeline-chart", "weather sales timeline chart"],
  ["#weather-sales-table", "weather sales table"],
  ["#pospal-overview", "pospal overview"],
  ["#open-close", "open close"],
  ["#calendar-grid", "calendar grid"],
  ["#discounts", "discounts"],
  ["#payment-mix", "payment mix"],
  ["#ticket-type", "ticket type"],
  ["#member-summary", "member summary"],
  ["#profit-ranking", "profit ranking"],
  ["#loss-reason-table", "loss reason table"],
  ["#exec-summary", "executive summary"],
  ["#dayparting-cards", "dayparting cards"],
  ["#product-bcg-chart", "product BCG chart"],
];

const fails = [];
if (!elementsBySel.get("#kpis")?._html.includes("净利润估算 = 实收金额")
  || !elementsBySel.get("#kpis")?._html.includes("不扣除运营管理比")) {
  fails.push("KPI band is missing the net-profit calculation tooltip");
}
if (!elementsBySel.get("#payment-mix")?._html.includes("单混合支付")
  || !elementsBySel.get("#payment-mix")?._html.includes("账款一致")) {
  fails.push("Payment mix is missing cashier reconciliation details");
}
if (!elementsBySel.get("#member-summary")?._html.includes("本金消费")
  || !elementsBySel.get("#member-summary")?._html.includes("赠送消费")) {
  fails.push("Member summary is missing card consumption details");
}
if (!elementsBySel.get("#weather-daily")?._html.includes("中雨")
  || !elementsBySel.get("#weather-daily")?._html.includes("逐日天气")
  || !elementsBySel.get("#weather-daily")?._html.includes("2025-06-06")
  || elementsBySel.get("#weather-daily")?._html.includes("收入")) {
  fails.push("Weather archive is missing daily history or still contains income analysis");
}
if (!elementsBySel.get("#weather-sales-summary")?._html.includes("雨天营收效应")
  || !elementsBySel.get("#weather-sales-summary")?._html.includes("最吸金天气")) {
  fails.push("Weather sales summary is missing impact cards");
}
const heatmapHtml = elementsBySel.get("#order-heatmap")?._html || "";
if (!heatmapHtml.includes('class="oh-hour-label">12</div>')
  || heatmapHtml.includes('class="oh-hour-label">9</div>')) {
  fails.push("Order heatmap did not hide the empty 9:00 hour");
}
const categoryHourHtml = elementsBySel.get("#cat-hour-heat")?._html || "";
if (!categoryHourHtml.includes('class="chh-hour-label">12</div>')
  || categoryHourHtml.includes('class="chh-hour-label">7</div>')
  || categoryHourHtml.includes('class="chh-hour-label">9</div>')) {
  fails.push("Category/hour heatmap did not hide the 7:00–9:00 period");
}
for (const [sel, name] of checks) {
  const el = elementsBySel.get(sel);
  if (!el) { fails.push(`MISSING: ${sel} (${name})`); continue; }
  if (!el._html || el._html.length < 5) {
    fails.push(`EMPTY: ${sel} (${name}) — html length=${el._html?.length}`);
  } else {
    console.log(`✓ ${name} (${sel}): ${el._html.length} bytes`);
  }
}

if (fails.length) {
  console.error("\nFAILURES:");
  fails.forEach((f) => console.error("  " + f));
  process.exit(1);
}
console.log("\nAll render targets filled successfully.");
process.exit(0);
