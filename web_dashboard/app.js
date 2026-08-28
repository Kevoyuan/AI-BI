/**
 * Boulangerie Ledger — primary Web Dashboard renderer.
 * Fetches the live same-origin Dashboard API and renders the production
 * tabbed interface with native HTML and SVG visualizations.
 */

const state = {
  payload: null,
  activeTab: "overview",
  activeRaw: "sales",
  activePreset: "month",
};

// Exposed for the AI assistant module (modules/ai.js) to read the live payload.
window.DashboardState = state;

const t = (value) => (window.I18n && typeof window.I18n.t === "function" ? window.I18n.t(value) : value);

window.addEventListener("languagechange", () => {
  if (state.payload) render(state.payload);
});

const numberFmt = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });
const moneyFmt = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 0,
});
const decimalFmt = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 1,
});
const decimalNumberFmt = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const percentFmt = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  maximumFractionDigits: 1,
});

// Brand palette mirrors CSS custom properties
const PALETTE = {
  revenue: "#98651A",   // bakery gold
  profit:  "#3F755F",   // celadon
  loss:    "#A84C3A",   // carmine
  card:    "#76526F",   // plum
  neutral: "#756D63",
  cats: ["#98651A", "#3F755F", "#A84C3A", "#76526F", "#BCA98E", "#756D63"],
};

/* ============================================================
   ECHARTS THEME & INSTANCE MANAGER
   ============================================================ */
const chartInstances = new Map(); // dom -> echarts instance

const chartResizeObserver = (typeof window !== "undefined" && typeof window.ResizeObserver === "function")
  ? new ResizeObserver((entries) => {
      for (const entry of entries) {
        const dom = entry.target;
        const inst = chartInstances.get(dom);
        if (inst && typeof inst.resize === "function") {
          try {
            if (!inst.isDisposed || !inst.isDisposed()) {
              inst.resize();
            }
          } catch (_) {}
        }
      }
    })
  : null;

const ECHARTS_THEME = {
  fontFamily: '"Inter Tight", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  monoFamily: '"JetBrains Mono", monospace',
  tooltip: {
    backgroundColor: "rgba(23, 14, 18, 0.94)",
    borderColor: "rgba(200, 155, 60, 0.35)",
    borderWidth: 1,
    padding: [10, 14],
    textStyle: {
      color: "#f5eee6",
      fontFamily: '"Inter Tight", sans-serif',
      fontSize: 12,
    },
    extraCssText: "box-shadow: 0 8px 24px rgba(0,0,0,0.55); backdrop-filter: blur(8px); border-radius: 8px;",
  },
  grid: {
    top: 36,
    left: 16,
    right: 20,
    bottom: 28,
    containLabel: true,
  },
  axisLine: {
    lineStyle: { color: "rgba(255, 255, 255, 0.12)" },
  },
  splitLine: {
    lineStyle: { color: "rgba(255, 255, 255, 0.05)", type: "dashed" },
  },
  axisLabel: {
    color: "#a89f91",
    fontFamily: '"JetBrains Mono", monospace',
    fontSize: 11,
  },
  axisPointer: {
    lineStyle: { color: "#c89b3c", type: "dashed", width: 1 },
    shadowStyle: { color: "rgba(200, 155, 60, 0.08)" },
  },
};

function getOrCreateChart(dom) {
  if (!dom || typeof window === "undefined" || !window.echarts) return null;
  let inst = chartInstances.get(dom) || window.echarts.getInstanceByDom(dom);
  if (!inst) {
    inst = window.echarts.init(dom, null, { renderer: "canvas" });
    chartInstances.set(dom, inst);
    if (chartResizeObserver) {
      try { chartResizeObserver.observe(dom); } catch (_) {}
    }
  }
  return inst;
}

function disposeChart(dom) {
  if (!dom) return;
  if (chartResizeObserver) {
    try { chartResizeObserver.unobserve(dom); } catch (_) {}
  }
  const inst = chartInstances.get(dom) || (window.echarts && window.echarts.getInstanceByDom(dom));
  if (inst) {
    try { inst.dispose(); } catch (_) {}
    chartInstances.delete(dom);
  }
}

function resizeAllCharts() {
  for (const [dom, inst] of chartInstances.entries()) {
    if (inst && typeof inst.resize === "function") {
      try {
        if (!inst.isDisposed || !inst.isDisposed()) {
          inst.resize();
        }
      } catch (_) {}
    }
  }
}

if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("resize", resizeAllCharts);
}

const els = {
  filters: document.querySelector("#filters"),
  year: document.querySelector("#year"),
  month: document.querySelector("#month"),
  dateFrom: document.querySelector("#date-from"),
  dateTo: document.querySelector("#date-to"),
  loading: document.querySelector("#loading"),
  content: document.querySelector("#content"),
  error: document.querySelector("#error"),
  statusCard: document.querySelector("#status-card"),
  statusTitle: document.querySelector("#status-title"),
  statusCopy: document.querySelector("#status-copy"),
  range: document.querySelector("#range-label"),
  updated: document.querySelector("#updated-at"),
  liveTime: document.querySelector("#live-time"),
  footStamp: document.querySelector("#foot-stamp"),
  kpis: document.querySelector("#kpis"),
  dailyChart: document.querySelector("#daily-chart"),
  dailyTable: document.querySelector("#daily-table"),
  hourChart: document.querySelector("#hour-chart"),
  incomeBars: document.querySelector("#income-bars"),
  incomeTable: document.querySelector("#income-table"),
  sourceDonut: document.querySelector("#source-donut"),
  sourceLegend: document.querySelector("#source-legend"),
  productBars: document.querySelector("#product-bars"),
  productTable: document.querySelector("#product-table"),
  lossList: document.querySelector("#loss-list"),
  cardChart: document.querySelector("#card-chart"),
  rechargeTable: document.querySelector("#recharge-table"),
  rawTable: document.querySelector("#raw-table"),
  rawTabs: document.querySelector("#raw-tabs"),
  legendDaily: document.querySelector("#legend-daily"),
  legendCard: document.querySelector("#legend-card"),
  downloadJson: document.querySelector("#download-json"),
  refresh: document.querySelector("#refresh-data"),
  // Cumulative + mined-from-app
  cumulative: document.querySelector("#cumulative"),
  cumChart: document.querySelector("#cum-chart"),
  orderHeatmap: document.querySelector("#order-heatmap"),
  hourPeriod: document.querySelector("#hour-period"),
  highValue: document.querySelector("#high-value"),
  ticketChart: document.querySelector("#ticket-chart"),
  lossByCategory: document.querySelector("#loss-by-category"),
  cardSummary: document.querySelector("#card-summary"),
  // Business insights
  alertsBanner: document.querySelector("#alerts-banner"),
  alertsList: document.querySelector("#alerts-list"),
  alertsCount: document.querySelector("#alerts-count"),
  searchOverlay: document.querySelector("#search-overlay"),
  searchInput: document.querySelector("#search-input"),
  searchResults: document.querySelector("#search-results"),
  searchBackdrop: document.querySelector("#search-backdrop"),
  anchorNav: document.querySelector("#anchor-nav"),
  heatmap: document.querySelector("#heatmap"),
  weekdayBars: document.querySelector("#weekday-bars"),
  categoryMargin: document.querySelector("#category-margin"),
  efficiency: document.querySelector("#efficiency"),
  lossAnomaly: document.querySelector("#loss-anomaly"),
  cardNetChart: document.querySelector("#card-net-chart"),
  abcSummary: document.querySelector("#abc-summary"),
  abcTable: document.querySelector("#abc-table"),
  slowTable: document.querySelector("#slow-table"),
  // Statistical
  volatility: document.querySelector("#volatility"),
  lorenzStats: document.querySelector("#lorenz-stats"),
  lorenzChart: document.querySelector("#lorenz-chart"),
  catHourHeat: document.querySelector("#cat-hour-heat"),
  orderAmountDist: document.querySelector("#order-amount-dist"),
  weatherDaily: document.querySelector("#weather-daily"),
  // Weather x Sales
  weatherSalesSummary: document.querySelector("#weather-sales-summary"),
  weatherSalesConditionChart: document.querySelector("#weather-sales-condition-chart"),
  weatherSalesScatterChart: document.querySelector("#weather-sales-scatter-chart"),
  weatherSalesTimelineChart: document.querySelector("#weather-sales-timeline-chart"),
  weatherSalesTable: document.querySelector("#weather-sales-table"),
  // Deep PosPal
  pospalOverview: document.querySelector("#pospal-overview"),
  openClose: document.querySelector("#open-close"),
  calendarGrid: document.querySelector("#calendar-grid"),
  discounts: document.querySelector("#discounts"),
  paymentMix: document.querySelector("#payment-mix"),
  ticketType: document.querySelector("#ticket-type"),
  memberSummary: document.querySelector("#member-summary"),
  profitRanking: document.querySelector("#profit-ranking"),
  lossReasonTable: document.querySelector("#loss-reason-table"),
  // Operations Upgrades
  execSummary: document.querySelector("#exec-summary"),
  daypartingCards: document.querySelector("#dayparting-cards"),
  productBcgChart: document.querySelector("#product-bcg-chart"),
};

// App state
const appState = {
  searchOpen: false,
  searchIndex: [],     // { id, tab, title, type }
  searchQuery: "",
  searchCursor: 0,
  jumpHighlightTimer: null,
};

/* ============================================================
   ANCHOR NAVIGATION + CMD+K SEARCH
   ============================================================ */

function buildSearchIndex() {
  appState.searchIndex = [];
  // Tabs
  document.querySelectorAll(".tab").forEach((btn) => {
    appState.searchIndex.push({
      id: null,
      tab: btn.dataset.tab,
      title: btn.textContent.trim(),
      type: "tab",
      keywords: ["tab", "视图"],
    });
  });
  // Panels
  document.querySelectorAll("[data-jump]").forEach((el) => {
    appState.searchIndex.push({
      id: el.id,
      tab: el.dataset.jump,
      title: el.dataset.title || el.querySelector("h3")?.textContent?.trim() || el.id,
      type: "panel",
      keywords: (el.dataset.title || "").split(" "),
    });
  });
  // KPI items
  document.querySelectorAll(".kpi").forEach((kpi, i) => {
    const label = kpi.querySelector(".kpi-label")?.textContent?.trim() || `KPI ${i + 1}`;
    appState.searchIndex.push({
      id: "kpis",
      tab: "overview",
      title: label,
      type: "kpi",
      keywords: ["kpi", "指标", label],
    });
  });
  // Top products
  if (state.payload?.topProducts) {
    state.payload.topProducts.slice(0, 30).forEach((p) => {
      appState.searchIndex.push({
        id: null,
        tab: "product",
        title: p["商品名称"],
        type: "product",
        keywords: ["商品", p["商品分类"] || "", p["收入分类"] || ""],
        meta: p,
      });
    });
  }
  // Income categories
  if (state.payload?.incomeCategories) {
    state.payload.incomeCategories.forEach((c) => {
      appState.searchIndex.push({
        id: null,
        tab: "income",
        title: c["收入分类"],
        type: "category",
        keywords: ["分类", "收入", c["收入分类"]],
      });
    });
  }
}

function openSearch() {
  if (appState.searchOpen) return;
  buildSearchIndex();
  appState.searchOpen = true;
  appState.searchQuery = "";
  appState.searchCursor = 0;
  els.searchOverlay.classList.remove("hidden");
  els.searchInput.value = "";
  renderSearchResults("");
  setTimeout(() => els.searchInput.focus(), 30);
}

function closeSearch() {
  if (!appState.searchOpen) return;
  appState.searchOpen = false;
  els.searchOverlay.classList.add("hidden");
  els.searchInput.value = "";
}

function renderSearchResults(query) {
  const q = (query || "").trim().toLowerCase();
  let matches = appState.searchIndex;
  if (q) {
    matches = matches.filter((it) => {
      const hay = `${it.title} ${(it.keywords || []).join(" ")}`.toLowerCase();
      return hay.includes(q);
    });
  }
  // Sort: tabs first, then panels, then products
  const order = { tab: 0, panel: 1, kpi: 2, category: 3, product: 4 };
  matches.sort((a, b) => (order[a.type] || 9) - (order[b.type] || 9));
  matches = matches.slice(0, 24);

  if (!matches.length) {
    els.searchResults.innerHTML = `<li class="search-empty">没有匹配项</li>`;
    return;
  }
  els.searchResults.innerHTML = matches
    .map((it, i) => {
      const icon = { tab: "▤", panel: "▦", kpi: "◆", category: "▣", product: "●" }[it.type] || "·";
      const tab = it.tab ? TABS_LABEL[it.tab] || it.tab : "";
      return `<li class="search-item ${i === appState.searchCursor ? "active" : ""}" data-idx="${i}">
        <span class="search-item-icon">${icon}</span>
        <span class="search-item-title">${escapeHtml(it.title)}</span>
        <span class="search-item-meta">${escapeHtml(it.type)}${tab ? " · " + escapeHtml(tab) : ""}</span>
      </li>`;
    })
    .join("");
  // Cache matches for keyboard nav
  appState._searchMatches = matches;
  els.searchResults.querySelectorAll(".search-item").forEach((el, i) => {
    el.addEventListener("click", () => activateSearchMatch(i));
    el.addEventListener("mouseenter", () => {
      appState.searchCursor = i;
      els.searchResults.querySelectorAll(".search-item").forEach((e, j) => e.classList.toggle("active", i === j));
    });
  });
}

const TABS_LABEL = {
  overview: "经营概览",
  income: "收入分类",
  product: "商品分析",
  loss: "报损与储值",
  insight: "业务洞察",
  raw: "明细",
};

function activateSearchMatch(i) {
  const m = appState._searchMatches?.[i];
  if (!m) return;
  closeSearch();
  if (m.tab) switchTab(m.tab);
  if (m.id) {
    setTimeout(() => highlightAndScroll(m.id), 60);
  } else if (m.type === "product" && m.meta) {
    setTimeout(() => highlightProductRow(m.meta["商品名称"]), 60);
  }
}

function highlightProductRow(name) {
  document.querySelectorAll(`#product-bars .product-bar .pname`).forEach((el) => {
    if (el.textContent.trim() === name) {
      const bar = el.closest(".product-bar");
      if (!bar) return;
      bar.scrollIntoView({ behavior: "smooth", block: "center" });
      bar.classList.add("jump-highlight");
      setTimeout(() => bar.classList.remove("jump-highlight"), 1800);
    }
  });
}

init().catch((e) => {
  console.error("init failed:", e);
});

async function init() {
  const now = new Date();
  const currentYear = now.getFullYear();
  for (let year = currentYear - 2; year <= currentYear; year += 1) {
    const opt = new Option(`${year}`, `${year}`, year === currentYear, year === currentYear);
    els.year.append(opt);
  }
  for (let month = 1; month <= 12; month += 1) {
    const selected = month === now.getMonth() + 1;
    const opt = new Option(
      `${String(month).padStart(2, "0")}月`,
      `${month}`,
      selected,
      selected
    );
    els.month.append(opt);
  }

  els.filters.addEventListener("submit", (e) => {
    e.preventDefault();
    if ((els.dateFrom.value && !els.dateTo.value) || (!els.dateFrom.value && els.dateTo.value)) {
      showError("请选择完整的开始日期和结束日期");
      return;
    }
    if (els.dateFrom.value && els.dateTo.value && els.dateFrom.value > els.dateTo.value) {
      showError("开始日期不能晚于结束日期");
      return;
    }
    // Form submit switches to manual year/month or custom date-range mode.
    // Uses the in-memory cache (no force_refresh) — clicking "本月" then
    // "今日" should feel instant, not trigger another xlsx download.
    state.activePreset = "";
    document.querySelectorAll(".preset").forEach((p) => p.classList.remove("active"));
    loadDashboard();
  });
  els.downloadJson.addEventListener("click", downloadJson);
  if (els.refresh) els.refresh.addEventListener("click", () => loadDashboard(true));

  // Preset bar
  document.querySelectorAll(".preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = btn.dataset.preset;
      if (state.activePreset === preset) return;
      state.activePreset = preset;
      els.dateFrom.value = "";
      els.dateTo.value = "";
      document.querySelectorAll(".preset").forEach((p) => p.classList.toggle("active", p === btn));
      loadDashboard();
    });
  });

  // Tab system
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  els.rawTabs.querySelectorAll(".raw-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchRaw(btn.dataset.raw));
  });

  // Anchor chip navigation
  if (els.anchorNav) {
    els.anchorNav.addEventListener("click", (e) => {
      const btn = e.target.closest(".anchor-chip");
      if (!btn) return;
      const id = btn.dataset.target;
      if (id) highlightAndScroll(id);
      // Mark active
      els.anchorNav.querySelectorAll(".anchor-chip").forEach((c) => c.classList.toggle("active", c === btn));
    });
  }

  // Search overlay: Cmd/Ctrl+K to open
  document.addEventListener("keydown", (e) => {
    const modKey = e.metaKey || e.ctrlKey;
    if (modKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (appState.searchOpen) closeSearch();
      else openSearch();
      return;
    }
    if (appState.searchOpen) {
      if (e.key === "Escape") {
        e.preventDefault();
        closeSearch();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        appState.searchCursor = Math.min((appState._searchMatches?.length || 1) - 1, appState.searchCursor + 1);
        renderSearchResults(els.searchInput.value);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        appState.searchCursor = Math.max(0, appState.searchCursor - 1);
        renderSearchResults(els.searchInput.value);
      } else if (e.key === "Enter") {
        e.preventDefault();
        activateSearchMatch(appState.searchCursor);
      }
    }
  });
  els.searchInput?.addEventListener("input", (e) => {
    appState.searchCursor = 0;
    renderSearchResults(e.target.value);
  });
  els.searchBackdrop?.addEventListener("click", closeSearch);
  els.searchOverlay?.querySelector(".search-esc")?.addEventListener("click", closeSearch);

  // Live clock
  updateLiveTime();
  setInterval(updateLiveTime, 1000);
  // Relative "updated X ago" timer
  setInterval(updateRelativeTime, 30 * 1000);

  loadDashboard();
}

function updateLiveTime() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  els.liveTime.textContent = `${hh}:${mm}:${ss}`;
}

let lastDataLoadedAt = null;
function updateRelativeTime() {
  if (!lastDataLoadedAt || !els.updated) return;
  const diff = Math.floor((Date.now() - lastDataLoadedAt) / 1000);
  if (diff < 5) {
    els.updated.textContent = `刚刚`;
  } else if (diff < 60) {
    els.updated.textContent = `${diff} 秒前`;
  } else if (diff < 3600) {
    els.updated.textContent = `${Math.floor(diff / 60)} 分钟前`;
  } else {
    els.updated.textContent = `${Math.floor(diff / 3600)} 小时前`;
  }
}

function switchTab(name) {
  state.activeTab = name;
  document.querySelectorAll(".tab").forEach((btn) => {
    const isActive = btn.dataset.tab === name;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === name);
  });
  requestAnimationFrame(resizeAllCharts);
  setTimeout(resizeAllCharts, 60);
  setTimeout(resizeAllCharts, 250);
}
if (typeof window !== "undefined") {
  window.switchTab = switchTab;
}

function switchRaw(name) {
  state.activeRaw = name;
  els.rawTabs.querySelectorAll(".raw-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.raw === name);
  });
  renderRawTable();
}

async function loadDashboard(refresh = false) {
  setLoading(true);
  try {
    const params = new URLSearchParams();
    if (state.activePreset) {
      params.set("preset", state.activePreset);
    } else if (els.dateFrom.value && els.dateTo.value) {
      params.set("date_from", els.dateFrom.value);
      params.set("date_to", els.dateTo.value);
      params.set("year", els.year.value);
      params.set("month", els.month.value);
    } else {
      params.set("year", els.year.value);
      params.set("month", els.month.value);
    }
    if (refresh) params.set("refresh", "1");
    const response = await fetch(`/api/dashboard?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "接口返回失败");
    state.payload = data;
    setLoading(false);
    render(data);
    requestAnimationFrame(resizeAllCharts);
    setTimeout(resizeAllCharts, 60);
    setTimeout(resizeAllCharts, 250);
    setStatus(
      refresh ? "额度保护刷新完成" : "接口已同步",
      refresh
        ? `${data.meta.source} · 缓存优先，当前月最多每 6 小时重新拉取一次`
        : `${data.meta.source} · ${data.meta.generatedAt}`,
    );
  } catch (error) {
    showError(error.message);
    setStatus("加载失败", error.message);
    setLoading(false);
  }
}

function setLoading(isLoading) {
  els.loading.classList.toggle("hidden", !isLoading);
  els.content.classList.toggle("hidden", isLoading);
  els.error.classList.add("hidden");
  if (els.refresh) els.refresh.disabled = isLoading;
  if (isLoading) {
    setStatus("正在加载", "正在从银豹后台接口读取数据。");
  }
}

function showError(message) {
  els.error.textContent = message;
  els.error.classList.remove("hidden");
  els.content.classList.add("hidden");
}

function setStatus(title, copy) {
  els.statusTitle.textContent = t(title);
  els.statusCopy.textContent = t(copy);
  els.statusCard.classList.toggle("is-loading", title === "正在加载");
  els.statusCard.classList.toggle("is-error", title === "加载失败");
}

function render(data) {
  els.range.textContent = `${data.meta.year} 年 ${String(data.meta.month).padStart(2, "0")} 月 · ${data.meta.range}`;
  els.updated.textContent = data.meta.generatedAt;
  lastDataLoadedAt = Date.now();
  updateRelativeTime();
  els.footStamp.textContent = `Generated ${data.meta.generatedAt} · ${data.meta.source}`;

  renderAlerts(data.alerts);
  renderExecSummary(data);
  renderKpis(data.kpis);
  renderLegend(els.legendDaily, [
    [t("实收金额"), PALETTE.revenue],
    [t("净利润估算"), PALETTE.profit],
    [t("损耗价值"), PALETTE.loss],
    [t("储值卡充值"), PALETTE.card],
  ]);
  renderMultiLine(els.dailyChart, data.daily, [
    { key: "实收金额", color: PALETTE.revenue },
    { key: "净利润估算", color: PALETTE.profit },
    { key: "损耗价值", color: PALETTE.loss },
    { key: "储值卡充值", color: PALETTE.card },
  ], { benchmark: data.weekendVsWeekday });
  renderPospalOverview(data.pospalOverview);
  renderHourChart(data.hourly);
  renderDaypartingGuide(data);
  renderDailyTable(data.daily);
  // Deep PosPal field mining
  renderOpenClose(data.openCloseHours);
  renderCalendar(data.calendar);
  renderDiscounts(data.discounts);
  renderPaymentMix(data.paymentMix);
  renderTicketType(data.ticketType);
  renderMemberSummary(data.memberSummary, data.cardBalance);
  renderBars(els.incomeBars, data.incomeCategories, "收入分类", "实收金额", "gold");
  renderIncomeTable(data.incomeCategories);
  renderDonut(els.sourceDonut, els.sourceLegend, data.sources);
  renderProductBars(data.topProducts);
  renderProductTable(data.topProducts);
  renderProfitRanking(data.profitByProduct);
  renderProductBCG(data.topProducts, data.profitByProduct, data.slowMovers, data.productABC);
  renderBars(els.lossList, data.lossReasons, "报损原因", "报损金额", "danger");
  renderLegend(els.legendCard, [
    [t("充值总金额"), PALETTE.revenue],
    [t("储值卡消费"), PALETTE.card],
  ]);
  renderMultiLine(els.cardChart, data.cards, [
    { key: "充值总金额", color: PALETTE.revenue },
    { key: "储值卡消费总金额", color: PALETTE.card },
  ], { showArea: true });
  renderRechargeTable(data.recharge);
  renderLossReasonTable(data.lossByReason);
  // Cumulative + mined-from-app
  renderCumulative(data.cumulative);
  renderOrderHeatmap(data.orderHeatmap);
  renderHourPeriod(data.hourPeriod);
  renderHighValue(data.highValueOrders);
  renderTicketChart(data.ticketDistribution);
  renderLossByCategory(data.lossByCategory);
  renderCardSummary(data.cardSummary);
  // Business insights
  renderHeatmap(data.weekdayPattern);
  renderWeekdayBars(data.weekendVsWeekday);
  renderCategoryMargin(data.categoryMargin);
  renderEfficiency(data.efficiency);
  renderLossAnomaly(data.lossDailyAnomaly);
  renderCardNetChart(data.cardNet);
  renderAbcSummary(data.productABC);
  renderAbcTable(data.productABC);
  renderSlowTable(data.slowMovers);
  // Statistical
  renderVolatility(data.volatility);
  renderLorenz(data.concentration);
  renderCategoryByHour(data.categoryByHour);
  renderOrderAmountDist(data.orderAmountDist);
  renderWeatherDaily(data.weatherDaily);
  renderWeatherSales(data.weatherSales, data);
  renderRawTable();
}

/* ============================================================
   EXECUTIVE SUMMARY BANNER
   ============================================================ */
function renderExecSummary(data) {
  if (!els.execSummary) return;
  if (!data || !data.kpis) {
    els.execSummary.innerHTML = "";
    els.execSummary.classList.add("hidden");
    return;
  }
  els.execSummary.classList.remove("hidden");
  const kpis = data.kpis;
  const rev = Number(kpis.revenue) || 0;
  const loss = Number(kpis.loss) || 0;
  const totalBase = rev + loss;
  const lossRate = totalBase > 0 ? (loss / totalBase) : 0;
  const lossPct = (lossRate * 100).toFixed(1);
  const lossStatus = lossRate > 0.08
    ? { text: "严重超标 ⚠️", cls: "pill-neg" }
    : (lossRate > 0.05 ? { text: "略微偏高 ⚡", cls: "pill-warn" } : { text: "健康区间 🌿", cls: "pill-pos" });

  const weekendRev = Number(data.weekendVsWeekday?.weekendRevenue) || 0;
  const weekendDays = Number(data.weekendVsWeekday?.weekendDays) || 1;
  const weekdayRev = Number(data.weekendVsWeekday?.weekdayRevenue) || 0;
  const weekdayDays = Number(data.weekendVsWeekday?.weekdayDays) || 1;
  const weekendDaily = weekendDays > 0 ? weekendRev / weekendDays : 0;
  const weekdayDaily = weekdayDays > 0 ? weekdayRev / weekdayDays : 0;
  const ratio = weekdayDaily > 0 ? (weekendDaily / weekdayDaily).toFixed(2) : "1.00";

  const slowCount = (data.slowMovers || []).length;
  const topProdName = (data.topProducts && data.topProducts[0]) ? data.topProducts[0]["商品名称"] : "招牌主力";

  els.execSummary.innerHTML = `
    <div class="exec-summary-card">
      <div class="exec-summary-head">
        <div class="exec-summary-title">
          <span class="exec-spark" aria-hidden="true">✦</span>
          <strong>经营简报与决策导向</strong>
        </div>
        <span class="exec-scope-badge">${escapeHtml(data.meta?.range || "当期经营")}</span>
      </div>
      <div class="exec-summary-grid">
        <div class="exec-item">
          <div class="exec-item-title">
            <span class="exec-icon">💰</span>
            <strong>营收与产出节奏</strong>
          </div>
          <p>当期实收 <strong>${escapeHtml(money(rev))}</strong>，周末日均产出是工作日的 <strong>${escapeHtml(ratio)} 倍</strong>。主力吸金王为 <em>「${escapeHtml(topProdName)}」</em>。</p>
        </div>
        <div class="exec-item">
          <div class="exec-item-title">
            <span class="exec-icon">🛡️</span>
            <strong>控损与健康度</strong>
          </div>
          <p>综合报损率 <strong>${escapeHtml(lossPct)}%</strong>（<span class="exec-status-pill ${lossStatus.cls}">${lossStatus.text}</span>），报损累计 <strong>${escapeHtml(money(loss))}</strong>。</p>
        </div>
        <div class="exec-item">
          <div class="exec-item-title">
            <span class="exec-icon">🥐</span>
            <strong>选品与优化建议</strong>
          </div>
          <p>已识别 <strong>${slowCount} 款</strong> 滞销/待观察尾部商品。<a href="#sec-product-bcg" class="exec-link-btn" data-tab="product" data-target="sec-product-bcg">查看波士顿四象限与淘汰建议 →</a></p>
        </div>
      </div>
    </div>
  `;

  els.execSummary.querySelectorAll(".exec-link-btn").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const tab = link.dataset.tab;
      const target = link.dataset.target;
      if (tab) switchTab(tab);
      if (target) highlightAndScroll(target);
    });
  });
}

/* ============================================================
   KPI BAND
   ============================================================ */
function renderKpis(kpis) {
  const deltas = state.payload?.kpiDeltas || {};
  const data = state.payload || {};
  const revenue = Number(kpis.revenue) || 0;
  const orders = Number(kpis.orders) || 0;
  const loss = Number(kpis.loss) || 0;
  const netProfit = Number(kpis.netProfit) || 0;
  const cardRecharge = Number(kpis.cardRecharge) || 0;
  const avgTicket = Number(kpis.avgTicket) || (orders > 0 ? revenue / orders : 0);

  // Operational metrics
  const totalBase = revenue + loss;
  const lossRate = totalBase > 0 ? (loss / totalBase) : 0;
  const lossHealthCls = lossRate > 0.08 ? "loss-danger" : (lossRate > 0.05 ? "loss-warn" : "loss-ok");
  const lossHealthText = lossRate > 0.08 ? t("高损预警") : (lossRate > 0.05 ? t("偏高") : t("健康"));

  // Units per transaction
  const topProds = data.topProducts || [];
  const totalUnits = topProds.reduce((sum, p) => sum + (Number(p["销售数量"]) || 0), 0);
  const upt = (orders > 0 && totalUnits > 0) ? (totalUnits / orders) : 0;
  const avgItemPrice = totalUnits > 0 ? (revenue / totalUnits) : 0;

  // Active days & daily average
  const dailyRows = data.daily || [];
  const activeDays = dailyRows.filter(d => Number(d["实收金额"]) > 0).length || dailyRows.length || 1;
  const avgDailyRevenue = activeDays > 0 ? (revenue / activeDays) : 0;

  const items = [
    {
      label: t("净利润估算"),
      value: money(netProfit),
      cls: "kpi-profit",
      suffix: "Net profit",
      subText: `${t("日均利润")} ${money(activeDays > 0 ? netProfit / activeDays : 0)}`,
      delta: deltas.netProfit,
      hasDelta: true,
      weight: 1,
      tooltip: "净利润估算 = 实收金额 − 商品总价 × 原料成本比 − 固定支出。按日计算后汇总，不扣除运营管理比。",
    },
    {
      label: t("实收金额"),
      value: money(revenue),
      cls: "kpi-revenue",
      suffix: "Revenue",
      subText: `${t("日均")} ${money(avgDailyRevenue)}`,
      delta: deltas.revenue,
      hasDelta: true,
      weight: 2,
    },
    {
      label: t("订单数"),
      value: number(orders),
      cls: "kpi-orders",
      suffix: "Orders",
      subText: `${t("日均")} ${number(Math.round(activeDays > 0 ? orders / activeDays : 0))} ${t("单")}`,
      delta: deltas.orders,
      hasDelta: true,
      weight: 3,
    },
    {
      label: t("客单价"),
      value: decimalFmt.format(avgTicket),
      cls: "kpi-ticket",
      suffix: "Avg ticket",
      subText: upt > 0 ? `${t("连带")} ${upt.toFixed(1)} ${t("件/单")} · ${t("件均")} ¥${avgItemPrice.toFixed(1)}` : t("客均消费"),
      delta: deltas.avgTicket,
      hasDelta: true,
      weight: 4,
    },
    {
      label: t("综合报损率"),
      value: percentFmt.format(lossRate),
      cls: `kpi-loss ${lossHealthCls}`,
      suffix: "Loss rate",
      subText: `${t("报损")} ${money(loss)} · ${lossHealthText}`,
      hasDelta: false,
      weight: 5,
      tooltip: "综合报损率 = 报损金额 ÷ (实收金额 + 报损金额)。行业建议健康线 <5%，5%~8% 为预警，>8% 需排查。",
    },
    {
      label: t("储值充值"),
      value: money(cardRecharge),
      cls: "kpi-card",
      suffix: "Recharge",
      subText: t("会员资金池沉淀"),
      hasDelta: false,
      weight: 6,
    },
  ];

  els.kpis.innerHTML = items
    .map((k) => {
      let deltaHtml = "";
      if (k.hasDelta && k.delta && k.delta.delta !== undefined) {
        const d = k.delta.delta;
        const trend = k.delta.trend;
        const arrow = trend === "up" ? "▲" : trend === "down" ? "▼" : "→";
        const cls = trend === "up" ? "up" : trend === "down" ? "down" : "flat";
        const sign = d > 0 ? "+" : "";
        deltaHtml = `<span class="kpi-delta ${cls}">${arrow} ${escapeHtml(sign)}${escapeHtml(percentFmt.format(d))}<em>后半月</em></span>`;
      }
      const tooltipHtml = k.tooltip
        ? `<button class="kpi-info" type="button" aria-label="查看计算公式" data-tooltip="${escapeHtml(k.tooltip)}" title="${escapeHtml(k.tooltip)}">?</button>`
        : "";
      const subHtml = k.subText ? `<span class="kpi-subtext">${escapeHtml(k.subText)}</span>` : "";
      return `
        <article class="kpi ${k.cls} weight-${k.weight}">
          <span class="kpi-label">${escapeHtml(k.label)}${tooltipHtml}</span>
          <strong class="kpi-value" data-counter="${Number((kpis.netProfit && k.cls.includes('kpi-profit')) ? kpis.netProfit : 0)}">${escapeHtml(k.value)}</strong>
          <span class="kpi-suffix">
            <span class="kpi-suffix-label">${escapeHtml(k.suffix)}</span>
            ${deltaHtml}
          </span>
          ${subHtml}
        </article>
      `;
    })
    .join("");
}

function renderAlerts(alerts) {
  if (!alerts || !alerts.length) {
    els.alertsBanner.classList.add("hidden");
    return;
  }
  els.alertsBanner.classList.remove("hidden");
  els.alertsCount.textContent = alerts.length;
  els.alertsList.innerHTML = alerts
    .map((a, i) => {
      // Pick a target by level / title
      const target = pickAlertTarget(a);
      return `
      <li class="alert-item alert-${escapeHtml(a.level)}" data-target="${target.id}" data-tab="${target.tab}">
        <span class="alert-bullet" aria-hidden="true"></span>
        <div class="alert-body">
          <strong>${escapeHtml(a.title)}</strong>
          <p>${escapeHtml(a.detail)}</p>
        </div>
        <button class="alert-jump" type="button" data-target="${target.id}" data-tab="${target.tab}">
          查看详情 →
        </button>
      </li>
    `;
    })
    .join("");
  // Wire jump buttons
  els.alertsList.querySelectorAll(".alert-jump, .alert-item").forEach((node) => {
    node.addEventListener("click", () => {
      const tab = node.dataset.tab;
      const id = node.dataset.target;
      if (tab) switchTab(tab);
      if (id) highlightAndScroll(id);
    });
  });
}

// Decide which panel an alert should jump to
function pickAlertTarget(a) {
  const title = (a.title || "").toLowerCase();
  const detail = (a.detail || "").toLowerCase();
  if (title.includes("报损") || detail.includes("报损率")) {
    return { tab: "insight", id: "p-20-报损异常日报" };
  }
  if (title.includes("净利润") || detail.includes("亏损")) {
    return { tab: "overview", id: "sec-daily" };
  }
  if (title.includes("订单")) {
    return { tab: "overview", id: "sec-hour" };
  }
  if (title.includes("储值")) {
    return { tab: "loss", id: null };
  }
  return { tab: "overview", id: null };
}

function highlightAndScroll(id) {
  const el = document.getElementById(id);
  if (!el) return;
  if (appState.jumpHighlightTimer) {
    clearTimeout(appState.jumpHighlightTimer);
  }
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.add("jump-highlight");
  appState.jumpHighlightTimer = setTimeout(() => {
    el.classList.remove("jump-highlight");
  }, 1800);
}

/* ============================================================
   LEGEND
   ============================================================ */
function renderLegend(target, items) {
  target.innerHTML = items
    .map(
      ([label, color]) => `<span><i style="background:${color}"></i>${escapeHtml(label)}</span>`
    )
    .join("");
}

/* ============================================================
   MULTI-LINE CHART (ECharts)
   ============================================================ */
function renderMultiLine(target, rows, series, opts = {}) {
  if (!rows || !rows.length) {
    disposeChart(target);
    target.innerHTML = empty("暂无数据");
    return;
  }

  const chart = getOrCreateChart(target);
  if (!chart) {
    renderMultiLineFallback(target, rows, series, opts);
    return;
  }

  const xData = rows.map((r) => r["日期"] || "");
  const hasZoom = rows.length > 14;

  const echartsSeries = series.map((s) => {
    const values = rows.map((r) => Number(r[s.key]) || 0);
    const item = {
      name: s.key,
      type: "line",
      smooth: 0.35,
      showSymbol: rows.length <= 31,
      symbolSize: 6,
      itemStyle: { color: s.color },
      lineStyle: { width: 2.2, color: s.color },
      data: values,
    };
    if (opts.showArea) {
      item.areaStyle = {
        color: (window.echarts?.graphic?.LinearGradient
          ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: s.color + "38" },
              { offset: 1, color: s.color + "02" },
            ])
          : s.color),
        opacity: 0.25,
      };
    }
    return item;
  });

  if (opts.benchmark && echartsSeries.length) {
    const bm = opts.benchmark;
    const weekdayAvg = (bm.weekdayDays && bm.weekdayDays > 0) ? (bm.weekdayRevenue / bm.weekdayDays) : 0;
    const weekendAvg = (bm.weekendDays && bm.weekendDays > 0) ? (bm.weekendRevenue / bm.weekendDays) : 0;
    const markLineData = [];
    if (weekdayAvg > 0) {
      markLineData.push({
        yAxis: Math.round(weekdayAvg),
        lineStyle: { color: "rgba(168, 159, 145, 0.7)", type: "dashed", width: 1.2 },
        label: {
          formatter: `工作日均 ${compactNumber(weekdayAvg)}`,
          position: "insideEndTop",
          color: "#a89f91",
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: 10,
        },
      });
    }
    if (weekendAvg > 0) {
      markLineData.push({
        yAxis: Math.round(weekendAvg),
        lineStyle: { color: "rgba(200, 155, 60, 0.8)", type: "dashed", width: 1.4 },
        label: {
          formatter: `周末均 ${compactNumber(weekendAvg)}`,
          position: "insideEndTop",
          color: "#c89b3c",
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: 10,
        },
      });
    }
    if (markLineData.length) {
      echartsSeries[0].markLine = {
        silent: true,
        symbol: "none",
        data: markLineData,
      };
    }
  }

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: ECHARTS_THEME.axisPointer,
      formatter: (params) => {
        if (!params || !params.length) return "";
        const date = params[0].axisValueLabel;
        let html = `<div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(date)}</div>`;
        for (const p of params) {
          const val = p.value;
          const marker = `<span style="display:inline-block;margin-right:6px;border-radius:50%;width:8px;height:8px;background-color:${p.color};"></span>`;
          html += `<div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">${marker}${escapeHtml(p.seriesName)}</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(val))}</strong>
          </div>`;
        }
        return html;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: opts.compact ? 20 : 28,
      bottom: hasZoom ? 42 : (opts.compact ? 20 : 28),
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: (val) => String(val).length > 5 ? String(val).slice(5) : val,
      },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: (v) => compactNumber(v),
      },
    },
    series: echartsSeries,
  };

  if (hasZoom) {
    option.dataZoom = [
      { type: "inside", start: 0, end: 100 },
      {
        type: "slider",
        height: 16,
        bottom: 6,
        borderColor: "transparent",
        backgroundColor: "rgba(255, 255, 255, 0.03)",
        fillerColor: "rgba(200, 155, 60, 0.2)",
        handleStyle: { color: "#c89b3c", borderColor: "#c89b3c" },
        textStyle: { color: "#a89f91", fontFamily: '"JetBrains Mono", monospace', fontSize: 10 },
      },
    ];
  }

  chart.setOption(option, true);
}

function renderMultiLineFallback(target, rows, series, opts = {}) {
  const width = 920;
  const height = opts.compact ? 240 : 320;
  const pad = { left: 64, right: 24, top: 16, bottom: 36 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const allValues = rows.flatMap((row) => series.map((s) => Number(row[s.key]) || 0));
  const max = Math.max(...allValues, 1);
  const min = Math.min(0, ...allValues);
  const range = max - min || 1;
  const x = (i) => pad.left + (rows.length === 1 ? innerW / 2 : (i / (rows.length - 1)) * innerW);
  const y = (v) => pad.top + innerH - ((Number(v) - min) / range) * innerH;
  const labelStep = Math.max(1, Math.ceil(rows.length / 10));
  const xLabels = rows
    .map((row, i) => {
      if (i % labelStep !== 0 && i !== rows.length - 1) return "";
      return `<text class="x-label" x="${x(i)}" y="${height - 12}" text-anchor="middle">${escapeHtml(row["日期"] || "")}</text>`;
    })
    .join("");
  const ticks = Array.from({ length: 5 }, (_, i) => i / 4);
  const grid = ticks
    .map((t) => {
      const yy = pad.top + innerH - t * innerH;
      return `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${yy}" y2="${yy}" />
              <text class="axis-label" x="${pad.left - 8}" y="${yy + 4}" text-anchor="end">${escapeHtml(compactNumber(max * t))}</text>`;
    })
    .join("");
  const paths = series
    .map((s) => {
      const points = rows.map((r, i) => `${x(i)},${y(r[s.key] || 0)}`).join(" ");
      const dots = rows
        .map(
          (r, i) =>
            `<circle class="series-dot" cx="${x(i)}" cy="${y(r[s.key] || 0)}" r="3.5" fill="${s.color}" style="color:${s.color}"><title>${escapeHtml(s.key)} · ${escapeHtml((r["日期"] || "").slice(5))} · ${escapeHtml(money(r[s.key] || 0))}</title></circle>`
        )
        .join("");
      let area = "";
      if (opts.showArea && rows.length > 1) {
        const areaPath = `M${x(0)},${pad.top + innerH} L${points} L${x(rows.length - 1)},${pad.top + innerH} Z`;
        area = `<path class="series-area" d="${areaPath}" fill="${s.color}" />`;
      }
      return `${area}<polyline class="series-line" points="${points}" stroke="${s.color}" />${dots}`;
    })
    .join("");

  target.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="趋势图">
      ${grid}
      ${paths}
      ${xLabels}
    </svg>
  `;
}

/* ============================================================
   HOUR CHART (ECharts)
   ============================================================ */
function renderHourChart(rows) {
  if (!rows || !rows.length) {
    disposeChart(els.hourChart);
    els.hourChart.innerHTML = empty("暂无数据");
    return;
  }

  const chart = getOrCreateChart(els.hourChart);
  if (!chart) {
    renderHourChartFallback(rows);
    return;
  }

  const byHour = new Map(rows.map((r) => [Number(r["小时"]), r]));
  const hours = Array.from({ length: 24 }, (_, h) => h);
  const revValues = hours.map((h) => Number(byHour.get(h)?.["实收金额"] || 0));
  const ordValues = hours.map((h) => Number(byHour.get(h)?.["订单数"] || 0));

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(200, 155, 60, 0.08)" } },
      formatter: (params) => {
        if (!params || !params.length) return "";
        const hour = params[0].axisValueLabel;
        const rev = params[0]?.value || 0;
        const ord = params[1]?.value || 0;
        const avg = ord > 0 ? rev / ord : 0;
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(hour)}:00 ${t("时段")}</div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">${t("营业实收")}</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(rev))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">${t("订单笔数")}</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${number(ord)} ${t("单")}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">${t("平均客单价")}</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(avg))}</strong>
          </div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 28,
      bottom: 24,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: hours.map((h) => `${h}`),
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: ECHARTS_THEME.axisLabel,
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: "value",
        position: "left",
        name: t("实收"),
        nameTextStyle: { color: "#a89f91", fontSize: 10 },
        axisLine: { show: false },
        splitLine: ECHARTS_THEME.splitLine,
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => compactNumber(v),
        },
      },
      {
        type: "value",
        position: "right",
        name: t("单数"),
        nameTextStyle: { color: "#a89f91", fontSize: 10 },
        axisLine: { show: false },
        splitLine: { show: false },
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => `${v}单`,
        },
      },
    ],
    series: [
      {
        name: t("营业实收"),
        type: "bar",
        yAxisIndex: 0,
        data: revValues,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "#c89b3c" },
                { offset: 1, color: "#5b8c7b" },
              ])
            : "#c89b3c"),
        },
        emphasis: {
          itemStyle: {
            color: "#f5eee6",
          },
        },
      },
      {
        name: t("订单数"),
        type: "line",
        yAxisIndex: 1,
        smooth: 0.3,
        showSymbol: false,
        symbolSize: 4,
        lineStyle: { width: 1.8, color: "#7a4e7d", type: "dashed" },
        itemStyle: { color: "#7a4e7d" },
        data: ordValues,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderHourChartFallback(rows) {
  const byHour = new Map(rows.map((r) => [Number(r["小时"]), r]));
  const max = Math.max(...rows.map((r) => Number(r["实收金额"]) || 0), 1);
  els.hourChart.innerHTML = Array.from({ length: 24 }, (_, hour) => {
    const row = byHour.get(hour);
    const value = Number(row?.["实收金额"] || 0);
    const orders = Number(row?.["订单数"] || 0);
    const pct = value / max;
    const heightPx = value > 0 ? Math.max(8, pct * 200) : 4;
    return `
      <div class="hour ${value === 0 ? "zero" : ""}" title="${hour}:00 · ${escapeHtml(money(value))} · ${orders} 单">
        <div class="hour-bar" style="height:${heightPx}px"></div>
        <span>${hour}</span>
      </div>
    `;
  }).join("");
}

/* ============================================================
   DAYPARTING STRATEGY & BAKING GUIDE
   ============================================================ */
function renderDaypartingGuide(data) {
  if (!els.daypartingCards) return;
  const periods = data?.hourPeriod || {};
  const catHours = data?.categoryByHour || [];

  const morningCats = {};
  const afternoonCats = {};
  const eveningCats = {};

  catHours.forEach((row) => {
    const h = Number(row["小时"]) || 0;
    const cat = row["收入分类"] || "其他";
    const amt = Number(row["实收金额"]) || 0;
    if (h >= 7 && h <= 10) morningCats[cat] = (morningCats[cat] || 0) + amt;
    else if (h >= 14 && h <= 17) afternoonCats[cat] = (afternoonCats[cat] || 0) + amt;
    else if (h >= 19 && h <= 22) eveningCats[cat] = (eveningCats[cat] || 0) + amt;
  });

  const getTopCatText = (catObj) => {
    const sorted = Object.entries(catObj).sort((a, b) => b[1] - a[1]);
    if (!sorted.length) return "烘焙常规单品";
    return sorted.slice(0, 2).map(([c, v]) => `${c} (${money(v)})`).join("、");
  };

  const mRev = periods.morning?.实收金额 || 0;
  const mPct = periods.morning?.占比 ? (periods.morning.占比 * 100).toFixed(1) : "0.0";
  const aRev = periods.afternoon?.实收金额 || 0;
  const aPct = periods.afternoon?.占比 ? (periods.afternoon.占比 * 100).toFixed(1) : "0.0";
  const eRev = periods.evening?.实收金额 || 0;
  const ePct = periods.evening?.占比 ? (periods.evening.占比 * 100).toFixed(1) : "0.0";

  els.daypartingCards.innerHTML = `
    <div class="dayparting-grid">
      <div class="dayparting-card dp-morning">
        <div class="dp-head">
          <span class="dp-badge">🌅 早市时段 (07:00 - 10:00)</span>
          <strong class="dp-amt">${escapeHtml(money(mRev))} <small>(${escapeHtml(mPct)}%)</small></strong>
        </div>
        <p class="dp-desc"><strong>主力品类：</strong>${escapeHtml(getTopCatText(morningCats))}</p>
        <div class="dp-action">
          <span class="dp-spark" aria-hidden="true">⚡</span>
          <span><strong>排产与陈列：</strong>吐司、现烤咸口主食建议在 07:30 前首炉出齐，主打早餐+咖啡超值组合。</span>
        </div>
      </div>

      <div class="dayparting-card dp-afternoon">
        <div class="dp-head">
          <span class="dp-badge">☕ 下午茶时段 (14:00 - 17:00)</span>
          <strong class="dp-amt">${escapeHtml(money(aRev))} <small>(${escapeHtml(aPct)}%)</small></strong>
        </div>
        <p class="dp-desc"><strong>主力品类：</strong>${escapeHtml(getTopCatText(afternoonCats))}</p>
        <div class="dp-action">
          <span class="dp-spark" aria-hidden="true">💡</span>
          <span><strong>排产与陈列：</strong>客单件数高峰期，重点陈列切片蛋糕、常温小点，前台强化连带推销话术。</span>
        </div>
      </div>

      <div class="dayparting-card dp-evening">
        <div class="dp-head">
          <span class="dp-badge">🌙 晚市与清盘 (19:00 - 22:00)</span>
          <strong class="dp-amt">${escapeHtml(money(eRev))} <small>(${escapeHtml(ePct)}%)</small></strong>
        </div>
        <p class="dp-desc"><strong>主力品类：</strong>${escapeHtml(getTopCatText(eveningCats))}</p>
        <div class="dp-action">
          <span class="dp-spark" aria-hidden="true">🛡️</span>
          <span><strong>排产与陈列：</strong>出单占比超 50% 且损耗最易发生，20:00 视余量启动阶梯折价，兼顾清盘与毛利。</span>
        </div>
      </div>
    </div>
  `;
}

/* ============================================================
   DAILY TABLE
   ============================================================ */
function renderDailyTable(rows) {
  if (!rows.length) {
    els.dailyTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  const cols = [
    { key: "日期", label: "日期" },
    { key: "实收金额", label: "实收", num: true, money: true },
    { key: "订单笔数", label: "订单", num: true },
    { key: "客单价", label: "客单价", num: true, money: true, decimals: true },
    { key: "商品成本估算", label: "成本", num: true, money: true },
    { key: "净利润估算", label: "净利润", num: true, money: true },
    { key: "损耗价值", label: "报损", num: true, money: true },
    { key: "报损率", label: "报损率", num: true, percent: true },
  ];
  els.dailyTable.innerHTML = tableHtml(rows, cols, { sortable: false });
}

/* ============================================================
   BAR LIST
   ============================================================ */
function renderBars(target, rows, labelKey, valueKey, variant) {
  if (!rows.length) {
    target.innerHTML = empty("暂无数据");
    return;
  }
  const max = Math.max(...rows.map((r) => Number(r[valueKey]) || 0), 1);
  target.innerHTML = rows
    .map((r, i) => {
      const value = Number(r[valueKey]) || 0;
      const pct = Math.max(2, (value / max) * 100);
      const variantCls = variant === "danger" ? "danger" : variant === "gold" && i === 0 ? "accent" : "";
      return `
        <div class="bar-row ${variantCls}" style="animation-delay:${i * 40}ms">
          <span class="name">${escapeHtml(r[labelKey] || "未分类")}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
          <span class="value">${escapeHtml(money(value))}</span>
        </div>
      `;
    })
    .join("");
}

/* ============================================================
   INCOME TABLE
   ============================================================ */
function renderIncomeTable(rows) {
  if (!rows.length) {
    els.incomeTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  const cols = [
    { key: "收入分类", label: "收入分类" },
    { key: "实收金额", label: "实收金额", num: true, money: true },
    { key: "订单数", label: "订单数", num: true },
    { key: "销售数量", label: "销售数量", num: true },
  ];
  els.incomeTable.innerHTML = tableHtml(rows, cols);
}

/* ============================================================
   DONUT (ECharts)
   ============================================================ */
function renderDonut(target, legend, rows) {
  if (!rows || !rows.length) {
    disposeChart(target);
    target.innerHTML = "";
    legend.innerHTML = empty("暂无数据");
    return;
  }

  const total = rows.reduce((s, r) => s + (Number(r["实收金额"]) || 0), 0);

  legend.innerHTML = rows
    .map((r, i) => {
      const value = Number(r["实收金额"]) || 0;
      const pct = total > 0 ? value / total : 0;
      return `
        <li>
          <span class="swatch" style="background:${PALETTE.cats[i % PALETTE.cats.length]}"></span>
          <span class="label">${escapeHtml(r["来源"])}</span>
          <span class="pct">${escapeHtml(percentFmt.format(pct))} · ${escapeHtml(money(value))}</span>
        </li>
      `;
    })
    .join("");

  const chart = getOrCreateChart(target);
  if (!chart) {
    renderDonutFallback(target, legend, rows);
    return;
  }

  const pieData = rows.map((r, i) => ({
    name: r["来源"] || "未知",
    value: Number(r["实收金额"]) || 0,
    itemStyle: {
      color: PALETTE.cats[i % PALETTE.cats.length],
      borderColor: "#170e12",
      borderWidth: 2,
      borderRadius: 4,
    },
  }));

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "item",
      ...ECHARTS_THEME.tooltip,
      formatter: (p) => `
        <div style="font-weight:600;margin-bottom:4px;color:#c89b3c;">${escapeHtml(p.name)}</div>
        <div style="display:flex;justify-content:space-between;gap:16px;font-size:12px;">
            <span style="color:#a89f91;">${t("金额")}</span>
          <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(p.value))}</strong>
        </div>
        <div style="display:flex;justify-content:space-between;gap:16px;font-size:12px;">
          <span style="color:#a89f91;">${t("占比")}</span>
          <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(percentFmt.format(total > 0 ? p.value / total : 0))}</strong>
        </div>
      `,
    },
    title: {
      text: compactMoney(total),
      subtext: "Total",
      left: "center",
      top: "38%",
      textStyle: {
        color: "#f5eee6",
        fontSize: 20,
        fontFamily: '"Fraunces", Georgia, serif',
        fontWeight: 500,
      },
      subtextStyle: {
        color: "#a89f91",
        fontSize: 10.5,
        fontFamily: '"JetBrains Mono", monospace',
        lineHeight: 12,
      },
    },
    series: [
      {
        name: t("来源分布"),
        type: "pie",
        radius: ["58%", "82%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: {
          scale: true,
          scaleSize: 6,
          label: { show: false },
        },
        data: pieData,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderDonutFallback(target, legend, rows) {
  const total = rows.reduce((s, r) => s + (Number(r["实收金额"]) || 0), 0);
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  const segments = rows
    .map((r, i) => {
      const value = Number(r["实收金额"]) || 0;
      const frac = total > 0 ? value / total : 0;
      const dash = frac * circumference;
      const segment = `<circle class="donut-segment" cx="100" cy="100" r="${radius}"
        stroke="${PALETTE.cats[i % PALETTE.cats.length]}"
        stroke-dasharray="${dash} ${circumference - dash}"
        stroke-dashoffset="${-offset}">
        <title>${escapeHtml(r["来源"])} · ${escapeHtml(money(value))} (${escapeHtml(percentFmt.format(frac))})</title>
      </circle>`;
      offset += dash;
      return segment;
    })
    .join("");

  target.innerHTML = `
    <svg viewBox="0 0 200 200" role="img" aria-label="来源分布">
      <circle cx="100" cy="100" r="${radius}" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="22" />
      ${segments}
    </svg>
    <div class="donut-center">
      <strong>${escapeHtml(money(total))}</strong>
      <span>Total</span>
    </div>
  `;
}

/* ============================================================
   PRODUCT BARS (Top 30) + TABLE
   ============================================================ */
function renderProductBars(rows) {
  if (!rows.length) {
    els.productBars.innerHTML = empty("暂无数据");
    return;
  }
  const max = Math.max(...rows.map((r) => Number(r["实收金额"]) || 0), 1);
  els.productBars.innerHTML = rows
    .map((r, i) => {
      const value = Number(r["实收金额"]) || 0;
      const pct = Math.max(2, (value / max) * 100);
      const cat = String(r["收入分类"] || "default").toLowerCase();
      const catCls = ["bakery", "beverage", "meal"].includes(cat) ? `cat-${cat}` : "cat-default";
      return `
        <div class="product-bar ${catCls}" style="animation-delay:${i * 30}ms">
          <div>
            <span class="pname">${escapeHtml(r["商品名称"] || "—")}</span>
            <span class="pcat">${escapeHtml(r["商品分类"] || "未分类")}</span>
          </div>
          <div class="ptrack"><div class="pfill" style="width:${pct}%"></div></div>
          <span class="pqty">${number(r["销售数量"] || 0)} 杯/件 · ${number(r["订单数"] || 0)} 单</span>
          <span class="pamt">${escapeHtml(money(value))}</span>
        </div>
      `;
    })
    .join("");
}

function renderProductTable(rows) {
  if (!rows.length) {
    els.productTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  const cols = [
    { key: "商品名称", label: "商品" },
    { key: "商品分类", label: "商品分类" },
    { key: "收入分类", label: "收入分类", cat: true },
    { key: "销售数量", label: "数量", num: true },
    { key: "订单数", label: "订单", num: true },
    { key: "实收金额", label: "实收", num: true, money: true },
  ];
  els.productTable.innerHTML = tableHtml(rows, cols);
}

/* ============================================================
   RECHARGE TABLE
   ============================================================ */
function renderRechargeTable(rows) {
  if (!rows.length) {
    els.rechargeTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  const cols = [
    { key: "支付分类", label: "支付分类" },
    { key: "充值金额", label: "充值金额", num: true, money: true },
    { key: "赠送金额", label: "赠送金额", num: true, money: true },
    { key: "笔数", label: "笔数", num: true },
  ];
  els.rechargeTable.innerHTML = tableHtml(rows, cols);
}

/* ============================================================
   CUMULATIVE & MINED-FROM-APP
   ============================================================ */

function renderCumulative(cum) {
  if (!cum) {
    els.cumulative.innerHTML = "";
    disposeChart(els.cumChart);
    return;
  }
  const items = [
    { label: t("商品总价累计"), value: money(cum["商品总价累计"]), cls: "cum-gross" },
    { label: t("实收金额累计"), value: money(cum["实收金额累计"]), cls: "cum-rev" },
    { label: t("订单笔数累计"), value: number(cum["订单笔数累计"]), cls: "cum-orders" },
    { label: t("损耗价值累计"), value: money(cum["损耗价值累计"]), cls: "cum-loss" },
    { label: t("净利润累计"), value: money(cum["净利润累计"]), cls: cum["净利润累计"] >= 0 ? "cum-profit-pos" : "cum-profit-neg" },
    { label: t("总净利润率"), value: `${(cum["总净利润率"] || 0).toFixed(1)}%`, cls: "cum-margin" },
  ];
  els.cumulative.innerHTML = items
    .map(
      (k) => `
      <article class="cum ${k.cls}">
        <span class="cum-label">${escapeHtml(k.label)}</span>
        <strong class="cum-value">${escapeHtml(k.value)}</strong>
      </article>
    `
    )
    .join("");

  const series = cum["series"] || [];
  if (!series.length) {
    disposeChart(els.cumChart);
    els.cumChart.innerHTML = empty("暂无数据");
    return;
  }

  const chart = getOrCreateChart(els.cumChart);
  if (!chart) {
    renderCumulativeFallback(cum);
    return;
  }

  const xData = series.map((r) => String(r["日期"]).slice(5));
  const values = series.map((r) => Number(r["净利润累计"]) || 0);
  const isAllPositive = values.every((v) => v >= 0);
  const isAllNegative = values.every((v) => v <= 0);
  const themeColor = isAllPositive ? "#5b8c7b" : isAllNegative ? "#c44536" : "#c89b3c";

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: ECHARTS_THEME.axisPointer,
      formatter: (params) => {
        if (!params || !params.length) return "";
        const row = series[params[0].dataIndex] || {};
        const val = params[0].value;
        const color = val >= 0 ? "#5b8c7b" : "#c44536";
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(row["日期"] || "")}</div>
          <div style="display:flex;justify-content:space-between;gap:18px;font-size:12px;">
            <span style="color:#a89f91;">${t("累计净利润")}</span>
            <strong style="color:${color};font-family:'JetBrains Mono',monospace;">${escapeHtml(money(val))}</strong>
          </div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 24,
      bottom: 28,
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: ECHARTS_THEME.axisLabel,
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: (v) => compactNumber(v),
      },
    },
    series: [
      {
        name: t("净利润累计"),
        type: "line",
        smooth: 0.3,
        showSymbol: series.length <= 31,
        symbolSize: 6,
        itemStyle: { color: themeColor },
        lineStyle: { width: 2.4, color: themeColor },
        areaStyle: {
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: themeColor + "40" },
                { offset: 1, color: themeColor + "05" },
              ])
            : themeColor),
        },
        markLine: {
          silent: true,
          symbol: "none",
          data: [{ yAxis: 0, lineStyle: { color: "#c89b3c", type: "dashed", width: 1 } }],
          label: { show: false },
        },
        data: values,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderCumulativeFallback(cum) {
  const series = cum["series"] || [];
  const width = 920;
  const height = 280;
  const pad = { left: 64, right: 24, top: 18, bottom: 32 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const values = series.map((r) => Number(r["净利润累计"]) || 0);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const x = (i) => pad.left + (series.length === 1 ? innerW / 2 : (i / (series.length - 1)) * innerW);
  const y = (v) => pad.top + innerH - ((v - min) / range) * innerH;

  const points = series.map((r, i) => `${x(i)},${y(Number(r["净利润累计"]) || 0)}`).join(" ");
  const zeroY = y(0);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const grid = ticks
    .map((t) => {
      const yy = pad.top + innerH - t * innerH;
      return `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${yy}" y2="${yy}" />
              <text class="axis-label" x="${pad.left - 8}" y="${yy + 4}" text-anchor="end">${escapeHtml(money(min + (max - min) * (1 - t)))}</text>`;
    })
    .join("");
  const labelStep = Math.max(1, Math.ceil(series.length / 10));
  const xLabels = series
    .map((r, i) => {
      if (i % labelStep !== 0 && i !== series.length - 1) return "";
      return `<text class="x-label" x="${x(i)}" y="${height - 8}" text-anchor="middle">${escapeHtml(String(r["日期"]).slice(5))}</text>`;
    })
    .join("");
  const color = (max >= 0 && min >= 0) ? "#5b8c7b" : (max <= 0 ? "#c44536" : "url(#cum-gradient)");
  const gradDef = `
    <defs>
      <linearGradient id="cum-gradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#5b8c7b" />
        <stop offset="100%" stop-color="#c44536" />
      </linearGradient>
    </defs>
  `;
  const zeroLine = `<line x1="${pad.left}" x2="${width - pad.right}" y1="${zeroY}" y2="${zeroY}" stroke="#c89b3c" stroke-dasharray="3 3" opacity="0.5" />`;
  const areaPath = series.length > 1
    ? `M${x(0)},${zeroY} L${points} L${x(series.length - 1)},${zeroY} Z`
    : "";
  const dots = series
    .map(
      (r, i) =>
        `<circle class="series-dot" cx="${x(i)}" cy="${y(Number(r["净利润累计"]) || 0)}" r="3.5" fill="${color}"><title>${escapeHtml(r["日期"])} · ${escapeHtml(money(r["净利润累计"]))}</title></circle>`
    )
    .join("");
  els.cumChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
      ${gradDef}
      ${grid}
      ${zeroLine}
      ${areaPath ? `<path d="${areaPath}" fill="${color}" opacity="0.18" />` : ""}
      <polyline class="series-line" points="${points}" stroke="${color}" />
      ${dots}
      ${xLabels}
    </svg>
  `;
}

function renderOrderHeatmap(rows) {
  if (!rows.length) {
    els.orderHeatmap.innerHTML = empty("暂无数据");
    return;
  }
  // Group by date
  const dateMap = new Map();
  for (const r of rows) {
    const date = String(r["日期"]);
    if (!dateMap.has(date)) dateMap.set(date, Array(24).fill(0));
    dateMap.get(date)[Number(r["小时"])] = Number(r["订单数"]) || 0;
  }
  const dates = [...dateMap.keys()].sort();
  const lastDates = dates.slice(-7); // last 7 days
  // Hide empty hour columns (for example, the store's unused 0–9 period).
  // Keep any hour that has a real order so an early-opening day is still visible.
  const hours = [...new Set(
    lastDates.flatMap((date) => {
      const cells = dateMap.get(date);
      return cells.reduce((visible, value, hour) => {
        if (value > 0) visible.push(hour);
        return visible;
      }, []);
    }),
  )].sort((a, b) => a - b);
  if (!hours.length) {
    els.orderHeatmap.innerHTML = empty("暂无订单时段");
    return;
  }
  const max = Math.max(
    ...lastDates.flatMap((date) => hours.map((hour) => dateMap.get(date)[hour] || 0)),
    1,
  );
  const gridStyle = `grid-template-columns: 40px repeat(${hours.length}, minmax(0, 1fr));`;

  function color(v) {
    if (v === 0) return "transparent";
    const t = v / max;
    return `rgba(200, 155, 60, ${(0.08 + t * 0.92).toFixed(3)})`;
  }
  // Show every other visible hour label to keep the compact grid readable.
  const hourLabels = hours.map((hour, index) => {
    const show = index % 2 === 0 || index === hours.length - 1;
    return show ? `<div class="oh-hour-label">${hour}</div>` : `<div class="oh-hour-label"></div>`;
  }).join("");

  const rowsHtml = lastDates
    .map((date) => {
      const cells = dateMap.get(date);
      const cellHtml = hours
        .map((hour) => {
          const v = cells[hour] || 0;
          return `<div class="oh-cell" style="background:${color(v)}" title="${escapeHtml(date)} ${hour}:00 · ${v} 单">${v > 0 ? `<span class="oh-val">${v}</span>` : ""}</div>`;
        })
        .join("");
      return `<div class="oh-row" style="${gridStyle}"><div class="oh-date">${escapeHtml(date.slice(5))}</div>${cellHtml}</div>`;
    })
    .join("");

  els.orderHeatmap.innerHTML = `
    <div class="oh-header" style="${gridStyle}">
      <div class="oh-date"></div>
      ${hourLabels}
    </div>
    ${rowsHtml}
    <div class="hm-legend" style="margin-top:8px">
          <span>${t("少")}</span><div class="hm-scale"></div><span>${t("多")}</span>
    </div>
  `;
}

function renderHourPeriod(period) {
  if (!period) {
    els.hourPeriod.innerHTML = empty("暂无数据");
    return;
  }
  const items = [
    { key: "morning", label: t("早市"), range: "9:30 – 12:00", color: "#c89b3c" },
    { key: "noon", label: t("午市"), range: "12:00 – 15:00", color: "#5b8c7b" },
    { key: "afternoon", label: t("下午"), range: "15:00 – 18:00", color: "#7a4e7d" },
    { key: "evening", label: t("晚市"), range: "18:00 – 24:00", color: "#c44536" },
  ];
  const total = items.reduce((s, it) => s + (period[it.key]?.["订单数"] || 0), 0) || 1;
  const max = Math.max(...items.map((it) => period[it.key]?.["订单数"] || 0), 1);

  const rows = items
    .map((it) => {
      const data = period[it.key] || { 订单数: 0, 实收金额: 0, 占比: 0 };
      const pct = Math.max(2, (data["订单数"] / max) * 100);
      return `
        <div class="hp-row">
          <div class="hp-label">
            <strong>${escapeHtml(it.label)}</strong>
            <span>${escapeHtml(it.range)}</span>
          </div>
          <div class="hp-bar"><div class="hp-fill" style="width:${pct}%; background:${it.color}"></div></div>
          <div class="hp-value">
            <span class="hp-main">${number(data["订单数"])} ${t("单")}</span>
            <span class="hp-sub">${escapeHtml(money(data["实收金额"]))} · ${escapeHtml(percentFmt.format(data["占比"]))}</span>
          </div>
        </div>
      `;
    })
    .join("");

  const peak = period["peak"] || { hour: 0, 订单数: 0 };
  els.hourPeriod.innerHTML = `
    <div class="hp-peak">
      <span class="hp-peak-label">${t("高峰时段")}</span>
      <strong>${peak.hour}:00</strong>
      <span class="hp-peak-sub">${number(peak["订单数"])} ${t("单")}</span>
    </div>
    <div class="hp-list">${rows}</div>
  `;
}

function renderHighValue(hv) {
  if (!hv) {
    els.highValue.innerHTML = empty("暂无数据");
    return;
  }
  const buckets = hv["buckets"] || [];
  const max = Math.max(...buckets.map((b) => Number(b["订单数"]) || 0), 1);
  const bars = buckets
    .map(
      (b) => `
      <div class="hv-row">
        <span class="hv-label">${escapeHtml(b["区间"])}</span>
        <div class="hv-track"><div class="hv-fill" style="width:${Math.max(2, (Number(b["订单数"]) / max) * 100)}%"></div></div>
        <span class="hv-value">${number(b["订单数"])}</span>
      </div>
    `
    )
    .join("");

  const stats = `
    <div class="hv-stats">
      <div><span>高价值订单数</span><strong>${number(hv["高价值订单数"])}</strong></div>
      <div><span>占总订单</span><strong>${escapeHtml(percentFmt.format(hv["高价值订单占比"] || 0))}</strong></div>
      <div><span>平均订单金额</span><strong>${escapeHtml(money(hv["平均订单金额"] || 0))}</strong></div>
      <div><span>高价值平均</span><strong>${escapeHtml(money(hv["高价值平均金额"] || 0))}</strong></div>
    </div>
  `;
  els.highValue.innerHTML = `${stats}<div class="hv-list">${bars}</div>`;
}

function renderTicketChart(rows) {
  if (!rows || !rows.length) {
    disposeChart(els.ticketChart);
    els.ticketChart.innerHTML = empty("暂无数据");
    return;
  }
  const data = rows.filter((r) => Number(r["订单数"]) > 0);
  if (!data.length) {
    disposeChart(els.ticketChart);
    els.ticketChart.innerHTML = empty("暂无数据");
    return;
  }

  const chart = getOrCreateChart(els.ticketChart);
  if (!chart) {
    renderTicketChartFallback(rows);
    return;
  }

  const xData = data.map((r) => `${r["小时"]}:00`);
  const values = data.map((r) => Number(r["客单价"]) || 0);

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: ECHARTS_THEME.axisPointer,
      formatter: (params) => {
        if (!params || !params.length) return "";
        const item = data[params[0].dataIndex];
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${item["小时"]}:00 ${t("时段")}</div>
          <div style="display:flex;justify-content:space-between;gap:18px;font-size:12px;">
            <span style="color:#a89f91;">${t("平均客单价")}</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(item["客单价"]))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;font-size:12px;">
            <span style="color:#a89f91;">${t("时段订单数")}</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${number(item["订单数"])} 单</strong>
          </div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 20,
      bottom: 24,
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: ECHARTS_THEME.axisLabel,
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: (v) => `¥${v}`,
      },
    },
    series: [
      {
        name: t("客单价"),
        type: "line",
        smooth: 0.35,
        showSymbol: true,
        symbolSize: 6,
        itemStyle: { color: "#c89b3c" },
        lineStyle: { width: 2.2, color: "#c89b3c" },
        areaStyle: {
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "rgba(200, 155, 60, 0.25)" },
                { offset: 1, color: "rgba(200, 155, 60, 0.02)" },
              ])
            : "rgba(200, 155, 60, 0.15)"),
        },
        data: values,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderTicketChartFallback(rows) {
  const data = rows.filter((r) => Number(r["订单数"]) > 0);
  const width = 480;
  const height = 240;
  const pad = { left: 50, right: 18, top: 16, bottom: 32 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const values = data.map((r) => Number(r["客单价"]) || 0);
  const max = Math.max(...values, 1);
  const min = 0;
  const range = max - min || 1;
  const x = (i) => pad.left + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
  const y = (v) => pad.top + innerH - ((v - min) / range) * innerH;

  const points = data.map((r, i) => `${x(i)},${y(r["客单价"] || 0)}`).join(" ");
  const dots = data
    .map(
      (r, i) =>
        `<circle class="series-dot" cx="${x(i)}" cy="${y(r["客单价"] || 0)}" r="3.5" fill="#c89b3c"><title>${r["小时"]}:00 · ${escapeHtml(money(r["客单价"]))}</title></circle>`
    )
    .join("");
  const ticks = [0, 0.5, 1];
  const grid = ticks
    .map((t) => {
      const yy = pad.top + innerH - t * innerH;
      return `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${yy}" y2="${yy}" />
              <text class="axis-label" x="${pad.left - 8}" y="${yy + 4}" text-anchor="end">${escapeHtml(money(max * t))}</text>`;
    })
    .join("");
  const labelStep = Math.max(1, Math.ceil(data.length / 8));
  const xLabels = data
    .map((r, i) => {
      if (i % labelStep !== 0 && i !== data.length - 1) return "";
      return `<text class="x-label" x="${x(i)}" y="${height - 8}" text-anchor="middle">${r["小时"]}:00</text>`;
    })
    .join("");

  els.ticketChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
      ${grid}
      <polyline class="series-line" points="${points}" stroke="#c89b3c" />
      ${dots}
      ${xLabels}
    </svg>
  `;
}

function renderLossByCategory(rows) {
  if (!rows || !rows.length) {
    els.lossByCategory.innerHTML = empty("本月无报废数据");
    return;
  }
  const max = Math.max(...rows.map((r) => Number(r["报损金额"]) || 0), 1);
  els.lossByCategory.innerHTML = rows
    .map(
      (r) => `
      <div class="bar-row">
        <span class="name">${escapeHtml(r["商品分类"] || "未分类")}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (Number(r["报损金额"] || 0) / max) * 100)}%; background: linear-gradient(90deg, #c89b3c 0%, #c44536 100%);"></div></div>
        <span class="value">${escapeHtml(money(r["报损金额"] || 0))}</span>
      </div>
    `
    )
    .join("");
}

function renderCardSummary(cs) {
  if (!cs) {
    els.cardSummary.innerHTML = empty("暂无储值卡数据");
    return;
  }
  const items = [
    { label: "充值总金额", value: cs["充值总金额"], color: "#c89b3c", cls: "cs-recharge" },
    { label: "储值卡消费", value: cs["储值卡消费"], color: "#7a4e7d", cls: "cs-spend" },
    { label: "本金消费", value: cs["本金消费"], color: "#5b8c7b", cls: "cs-principal" },
    { label: "赠送消费", value: cs["赠送消费"], color: "#c44536", cls: "cs-gift" },
  ];
  const total = (cs["本金消费"] || 0) + (cs["赠送消费"] || 0) || 1;

  // Stacked bar showing principal vs gift in total spend
  const spend = cs["储值卡消费"] || 0;
  const principalRatio = (cs["本金消费"] || 0) / total;
  const giftRatio = (cs["赠送消费"] || 0) / total;

  els.cardSummary.innerHTML = `
    <div class="cs-grid">
      ${items
        .map(
          (k) => `
        <div class="cs-cell ${k.cls}">
          <span class="cs-label">${escapeHtml(k.label)}</span>
          <strong class="cs-value">${escapeHtml(money(k.value))}</strong>
        </div>
      `
        )
        .join("")}
    </div>
    <div class="cs-stack">
      <div class="cs-stack-head">储值消费本金 vs 赠送占比</div>
      <div class="cs-bar">
        <div class="cs-bar-principal" style="width:${(principalRatio * 100).toFixed(1)}%; background:#5b8c7b"></div>
        <div class="cs-bar-gift" style="width:${(giftRatio * 100).toFixed(1)}%; background:#c44536"></div>
      </div>
      <div class="cs-stack-legend">
        <span><i style="background:#5b8c7b"></i>本金 ${escapeHtml(percentFmt.format(principalRatio))}</span>
        <span><i style="background:#c44536"></i>赠送 ${escapeHtml(percentFmt.format(giftRatio))}</span>
      </div>
    </div>
  `;
}

/* ============================================================
   BUSINESS INSIGHTS
   ============================================================ */

function renderHeatmap(rows) {
  if (!rows.length) {
    els.heatmap.innerHTML = empty("暂无数据");
    return;
  }
  // Group by ISO week
  const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
  // Find min/max
  const values = rows.map((r) => Number(r["实收金额"]) || 0);
  const max = Math.max(...values, 1);

  // Sort dates, compute week index from day of month
  const sorted = [...rows].sort((a, b) => String(a["日期"]).localeCompare(String(b["日期"])));
  // Group by week-of-month. First week is seeded with leading nulls up to the first day's dow.
  const weeks = [];
  let current = null;
  for (const r of sorted) {
    const d = new Date(r["日期"]);
    const dow = Number(r["周几"]); // 0=Mon, 6=Sun
    if (current === null) {
      current = { cells: Array(7).fill(null), startDate: d };
      weeks.push(current);
      // Seed leading empty cells
      for (let i = 0; i < dow; i += 1) {
        // cell stays null
      }
    } else if (dow === 0) {
      current = { cells: Array(7).fill(null), startDate: d };
      weeks.push(current);
    }
    current.cells[dow] = r;
  }
  if (!weeks.length) {
    els.heatmap.innerHTML = empty("暂无数据");
    return;
  }
  // Limit to last 6 weeks for display
  const displayWeeks = weeks.slice(-6);

  // Build color scale
  function color(v) {
    if (v === null) return "transparent";
    const t = v / max;
    // gold scale from transparent to solid
    const alpha = 0.08 + t * 0.92;
    return `rgba(200, 155, 60, ${alpha.toFixed(3)})`;
  }

  const rowsHtml = displayWeeks
    .map((wk, wi) => {
      const cells = wk.cells
        .map((cell, di) => {
          if (cell === null) return `<div class="hm-cell empty"></div>`;
          const v = Number(cell["实收金额"]) || 0;
          const orders = Number(cell["订单数"]) || 0;
          const dt = cell["日期"] || "";
          return `<div class="hm-cell" style="background:${color(v)}" title="${escapeHtml(dt)} · 周${weekdays[di]} · ${escapeHtml(money(v))} · ${orders} 单">
            <span class="hm-val">${escapeHtml(money(v).replace("¥", "¥"))}</span>
          </div>`;
        })
        .join("");
      return `<div class="hm-row"><div class="hm-row-label">W${wi + 1}</div>${cells}</div>`;
    })
    .join("");

  const header = weekdays.map((d) => `<div class="hm-cell-label">${d}</div>`).join("");

  els.heatmap.innerHTML = `
    <div class="hm-header">
      <div class="hm-row-label"></div>
      ${header}
    </div>
    ${rowsHtml}
    <div class="hm-legend">
      <span>少</span>
      <div class="hm-scale"></div>
      <span>多</span>
    </div>
  `;
}

function renderWeekdayBars(wvw) {
  if (!wvw || (!wvw.weekdayRevenue && !wvw.weekendRevenue)) {
    els.weekdayBars.innerHTML = empty("暂无数据");
    return;
  }
  const wdAvg = wvw.weekdayDays > 0 ? wvw.weekdayRevenue / wvw.weekdayDays : 0;
  const weAvg = wvw.weekendDays > 0 ? wvw.weekendRevenue / wvw.weekendDays : 0;
  const wdOrdersAvg = wvw.weekdayDays > 0 ? wvw.weekdayOrders / wvw.weekdayDays : 0;
  const weOrdersAvg = wvw.weekendDays > 0 ? wvw.weekendOrders / wvw.weekendDays : 0;
  const maxRev = Math.max(wdAvg, weAvg, 1);
  const maxOrd = Math.max(wdOrdersAvg, weOrdersAvg, 1);

  function bar(label, days, value, avg, maxVal, formatter, color) {
    const pct = Math.max(2, (avg / maxVal) * 100);
    return `
      <div class="wday-row">
        <div class="wday-label">
          <strong>${label}</strong>
          <span>${days} 天</span>
        </div>
        <div class="wday-bar" style="--bar-color:${color}">
          <div class="wday-fill" style="width:${pct}%"></div>
        </div>
        <div class="wday-value">
          <span class="wday-main">${escapeHtml(formatter(avg))}</span>
          <span class="wday-sub">日均 · 总额 ${escapeHtml(formatter(value))}</span>
        </div>
      </div>
    `;
  }
  els.weekdayBars.innerHTML = `
    <div class="wday-meta">
      <div><span>对比</span><strong>日均实收</strong></div>
    </div>
    ${bar("工作日", wvw.weekdayDays, wvw.weekdayRevenue, wdAvg, maxRev, money, "#5b8c7b")}
    ${bar("周末", wvw.weekendDays, wvw.weekendRevenue, weAvg, maxRev, money, "#c89b3c")}
    <div class="wday-meta" style="margin-top:18px">
      <div><span>对比</span><strong>日均订单</strong></div>
    </div>
    ${bar("工作日", wvw.weekdayDays, wvw.weekdayOrders, wdOrdersAvg, maxOrd, (v) => number(Math.round(v)), "#5b8c7b")}
    ${bar("周末", wvw.weekendDays, wvw.weekendOrders, weOrdersAvg, maxOrd, (v) => number(Math.round(v)), "#c89b3c")}
  `;
}

function renderCategoryMargin(rows) {
  if (!rows.length) {
    els.categoryMargin.innerHTML = empty("暂无数据");
    return;
  }
  const max = Math.max(...rows.map((r) => Number(r["实收金额"]) || 0), 1);
  els.categoryMargin.innerHTML = rows
    .map((r) => {
      const rev = Number(r["实收金额"]) || 0;
      const margin = Number(r["毛利率"]) || 0;
      const pct = Math.max(2, (rev / max) * 100);
      const marginPct = (margin * 100).toFixed(1);
      return `
        <div class="bar-row">
          <span class="name">${escapeHtml(r["收入分类"])} <em class="margin-tag">毛利 ${marginPct}%</em></span>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
          <span class="value">${escapeHtml(money(rev))}</span>
        </div>
      `;
    })
    .join("");
}

function renderEfficiency(eff) {
  if (!eff) {
    els.efficiency.innerHTML = empty("暂无数据");
    return;
  }
  const profitMargin = (Number(eff.profitMargin) || 0) * 100;
  const costRatio = (Number(eff.costRatio) || 0) * 100;
  const profitPct = Math.max(0, Math.min(100, profitMargin));
  const opDays = Number(eff.operatingDays) || 0;
  const breakeven = Number(eff.breakevenDays) || 0;
  const breakevenPct = opDays > 0 ? (breakeven / opDays) * 100 : 0;

  els.efficiency.innerHTML = `
    <div class="eff-grid">
      <div class="eff-cell eff-gauge-wrap">
        <div id="eff-gauge" class="gauge" style="width: 100%; height: 200px; min-height: 200px;"></div>
      </div>
      <div class="eff-cell">
        <div class="eff-stat">
          <span class="eff-stat-label">成本占比</span>
          <strong class="eff-stat-value">${costRatio.toFixed(1)}%</strong>
          <div class="eff-stat-track"><div class="eff-stat-fill" style="width:${Math.min(100, costRatio)}%; background:${costRatio > 80 ? "#c44536" : costRatio > 65 ? "#d36f31" : "#5b8c7b"}"></div></div>
        </div>
        <div class="eff-stat">
          <span class="eff-stat-label">盈利日数 / 营业日数</span>
          <strong class="eff-stat-value">${breakeven} / ${opDays}</strong>
          <div class="eff-stat-track"><div class="eff-stat-fill" style="width:${breakevenPct}%; background:#5b8c7b"></div></div>
        </div>
        <div class="eff-stat">
          <span class="eff-stat-label">本月总成本</span>
          <strong class="eff-stat-value">${escapeHtml(money(eff.totalCost))}</strong>
        </div>
        <div class="eff-stat">
          <span class="eff-stat-label">本月总收入</span>
          <strong class="eff-stat-value">${escapeHtml(money(eff.totalRevenue))}</strong>
        </div>
      </div>
    </div>
  `;

  const gaugeDom = els.efficiency.querySelector("#eff-gauge");
  if (!gaugeDom) return;

  const chart = getOrCreateChart(gaugeDom);
  if (!chart) {
    renderEfficiencyFallback(gaugeDom, profitMargin);
    return;
  }

  const option = {
    animationDuration: 600,
    series: [
      {
        type: "gauge",
        startAngle: 190,
        endAngle: -10,
        min: 0,
        max: 50,
        splitNumber: 5,
        radius: "95%",
        center: ["50%", "65%"],
        itemStyle: {
          color: profitMargin >= 20 ? "#3F755F" : profitMargin >= 10 ? "#98651A" : "#A84C3A",
        },
        progress: {
          show: true,
          roundCap: true,
          width: 14,
        },
        pointer: {
          show: true,
          length: "60%",
          width: 4,
          itemStyle: { color: "#98651A" },
        },
        axisLine: {
          roundCap: true,
          lineStyle: {
            width: 14,
            color: [[1, "rgba(151, 141, 128, 0.18)"]],
          },
        },
        axisTick: { show: false },
        splitLine: {
          length: 6,
          lineStyle: { width: 1.5, color: "rgba(151, 141, 128, 0.4)" },
        },
        axisLabel: {
          distance: 14,
          color: "#756D63",
          fontSize: 11,
          fontFamily: '"JetBrains Mono", monospace',
          formatter: "{value}%",
        },
        title: {
          show: true,
          offsetCenter: [0, "-15%"],
          fontSize: 12,
          fontWeight: "500",
          color: "#756D63",
          fontFamily: '"Inter Tight", "PingFang SC", sans-serif',
        },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, "-45%"],
          fontSize: 26,
          fontWeight: "bold",
          formatter: "{value}%",
          color: "#2D2924",
          fontFamily: '"Fraunces", "Songti SC", serif',
        },
        data: [
          {
            value: Math.round(profitMargin * 10) / 10,
            name: "净利润率",
          },
        ],
      },
    ],
  };

  chart.setOption(option, true);
  requestAnimationFrame(() => {
    try {
      chart.resize();
    } catch (_) {}
  });
}

function renderEfficiencyFallback(target, profitMargin) {
  const dialSize = 180;
  const radius = 70;
  const cx = dialSize / 2;
  const cy = dialSize / 2 + 10;
  const startAngle = Math.PI;
  const profitFrac = Math.max(0, Math.min(1, profitMargin / 50));
  const profitAngle = startAngle - profitFrac * Math.PI;
  function polar(angle, r) {
    return [cx + Math.cos(angle) * r, cy - Math.sin(angle) * r];
  }
  const [x1, y1] = polar(startAngle, radius);
  const [x2, y2] = polar(0, radius);
  const [px, py] = polar(profitAngle, radius);
  const profitLargeArc = profitFrac > 0.5 ? 1 : 0;
  const themeColor = profitMargin >= 20 ? "#3F755F" : profitMargin >= 10 ? "#98651A" : "#A84C3A";
  target.innerHTML = `
    <svg viewBox="0 0 ${dialSize} ${dialSize / 2 + 20}" class="gauge" style="width: 100%; height: 200px;">
      <path d="M${x1},${y1} A${radius},${radius} 0 0 1 ${x2},${y2}" fill="none" stroke="rgba(151, 141, 128, 0.18)" stroke-width="14" stroke-linecap="round" />
      <path d="M${x1},${y1} A${radius},${radius} 0 ${profitLargeArc} 1 ${px},${py}" fill="none" stroke="${themeColor}" stroke-width="14" stroke-linecap="round" />
      <text x="${cx}" y="${cy - 30}" style="font-family:var(--serif); font-size:24px; fill:var(--ink); font-weight:bold;" text-anchor="middle">${profitMargin.toFixed(1)}%</text>
      <text x="${cx}" y="${cy - 12}" style="font-family:var(--sans); font-size:11px; fill:var(--muted); letter-spacing:0.1em;" text-anchor="middle">净利润率</text>
    </svg>
  `;
}

function renderLossAnomaly(rows) {
  if (!rows.length) {
    els.lossAnomaly.innerHTML = empty("本月无报损数据");
    return;
  }
  const maxRate = Math.max(...rows.map((r) => Number(r["报损率"]) || 0), 0.01);
  els.lossAnomaly.innerHTML = rows
    .map((r) => {
      const rate = Number(r["报损率"]) || 0;
      const loss = Number(r["损耗价值"]) || 0;
      const sev = r["严重程度"] || "ok";
      const fillPct = Math.max(2, (rate / maxRate) * 100);
      const cls = sev === "critical" ? "critical" : sev === "warn" ? "warn" : "ok";
      return `
        <div class="anomaly-row ${cls}">
          <span class="anomaly-date">${escapeHtml(String(r["日期"]).slice(5))}</span>
          <div class="anomaly-track"><div class="anomaly-fill" style="width:${fillPct}%"></div></div>
          <span class="anomaly-rate">${(rate * 100).toFixed(1)}%</span>
          <span class="anomaly-amt">${escapeHtml(money(loss))}</span>
          ${sev !== "ok" ? `<span class="anomaly-tag">${sev === "critical" ? "严重" : "偏高"}</span>` : ""}
        </div>
      `;
    })
    .join("");
}

/* ============================================================
   CARD NET CHART (ECharts)
   ============================================================ */
function renderCardNetChart(rows) {
  if (!rows || !rows.length) {
    disposeChart(els.cardNetChart);
    els.cardNetChart.innerHTML = empty("暂无储值卡数据");
    return;
  }

  const chart = getOrCreateChart(els.cardNetChart);
  if (!chart) {
    renderCardNetChartFallback(rows);
    return;
  }

  const xData = rows.map((r) => String(r["日期"]).slice(5));
  const netValues = rows.map((r) => Number(r["净值"]) || 0);
  const cumValues = rows.map((r) => Number(r["累计余额"]) || 0);

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: ECHARTS_THEME.axisPointer,
      formatter: (params) => {
        if (!params || !params.length) return "";
        const row = rows[params[0].dataIndex] || {};
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(row["日期"] || "")}</div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#5b8c7b;">● 当日净值</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(row["净值"]))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#c89b3c;">● 累计余额</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(row["累计余额"]))}</strong>
          </div>
        `;
      },
    },
    legend: {
      show: true,
      top: 0,
      right: 12,
      textStyle: { color: "#a89f91", fontSize: 11 },
      itemWidth: 14,
      itemHeight: 4,
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 30,
      bottom: 24,
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: ECHARTS_THEME.axisLabel,
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: (v) => compactNumber(v),
      },
    },
    series: [
      {
        name: "当日净值",
        type: "line",
        smooth: 0.3,
        showSymbol: rows.length <= 31,
        symbolSize: 5,
        itemStyle: { color: "#5b8c7b" },
        lineStyle: { width: 2, color: "#5b8c7b" },
        data: netValues,
      },
      {
        name: "累计余额",
        type: "line",
        smooth: 0.3,
        showSymbol: rows.length <= 31,
        symbolSize: 5,
        itemStyle: { color: "#c89b3c" },
        lineStyle: { width: 2, color: "#c89b3c" },
        areaStyle: {
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "rgba(200, 155, 60, 0.2)" },
                { offset: 1, color: "rgba(200, 155, 60, 0.02)" },
              ])
            : "rgba(200, 155, 60, 0.1)"),
        },
        markLine: {
          silent: true,
          symbol: "none",
          data: [{ yAxis: 0, lineStyle: { color: "#c89b3c", type: "dashed", width: 1 } }],
          label: { show: false },
        },
        data: cumValues,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderCardNetChartFallback(rows) {
  const width = 520;
  const height = 240;
  const pad = { left: 56, right: 18, top: 18, bottom: 30 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const allValues = rows.flatMap((r) => [Number(r["净值"]) || 0, Number(r["累计余额"]) || 0]);
  const max = Math.max(...allValues, 0);
  const min = Math.min(...allValues, 0);
  const range = max - min || 1;

  const x = (i) => pad.left + (rows.length === 1 ? innerW / 2 : (i / (rows.length - 1)) * innerW);
  const y = (v) => pad.top + innerH - ((v - min) / range) * innerH;

  const netPoints = rows.map((r, i) => `${x(i)},${y(r["净值"] || 0)}`).join(" ");
  const cumPoints = rows.map((r, i) => `${x(i)},${y(r["累计余额"] || 0)}`).join(" ");

  const labelStep = Math.max(1, Math.ceil(rows.length / 8));
  const xLabels = rows
    .map((r, i) => {
      if (i % labelStep !== 0 && i !== rows.length - 1) return "";
      return `<text class="x-label" x="${x(i)}" y="${height - 10}" text-anchor="middle">${escapeHtml(String(r["日期"]).slice(5))}</text>`;
    })
    .join("");

  const zeroY = y(0);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const grid = ticks
    .map((t) => {
      const yy = pad.top + innerH - t * innerH;
      return `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${yy}" y2="${yy}" />
              <text class="axis-label" x="${pad.left - 8}" y="${yy + 4}" text-anchor="end">${escapeHtml(money(min + (max - min) * (1 - t)))}</text>`;
    })
    .join("");

  const zeroLine = `<line x1="${pad.left}" x2="${width - pad.right}" y1="${zeroY}" y2="${zeroY}" stroke="#c89b3c" stroke-dasharray="3 3" opacity="0.6" />`;

  els.cardNetChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="储值卡余额">
      ${grid}
      ${zeroLine}
      <polyline class="series-line" points="${netPoints}" stroke="#5b8c7b" />
      <polyline class="series-line" points="${cumPoints}" stroke="#c89b3c" />
      ${xLabels}
    </svg>
  `;
}

function renderVolatility(v) {
  if (!v || !v.days) {
    els.volatility.innerHTML = empty("暂无数据");
    return;
  }
  const cv = v.cv || 0;
  const cvTag = cv < 0.10 ? { label: "极稳定", color: "var(--celadon)" }
    : cv < 0.20 ? { label: "稳定", color: "var(--celadon)" }
    : cv < 0.35 ? { label: "波动", color: "var(--gold)" }
    : { label: "高波动", color: "var(--carmine)" };

  const skew = v.skewness || 0;
  const skewTag = skew > 0.5 ? "右偏（少数日拉高）" : skew < -0.5 ? "左偏（少数日拉低）" : "近对称";

  const stats = [
    { label: "营业日数", value: v.days, kind: "num" },
    { label: "日均实收", value: money(v.mean), kind: "money", highlight: true },
    { label: "中位数", value: money(v.median), kind: "money" },
    { label: "标准差", value: money(v.std), kind: "money" },
    { label: "变异系数 CV", value: `${(cv * 100).toFixed(1)}%`, kind: "text", sub: cvTag.label, color: cvTag.color },
    { label: "极差", value: money(v.range), kind: "money" },
    { label: "四分位距 IQR", value: money(v.iqr), kind: "money" },
    { label: "偏度", value: skew.toFixed(2), kind: "text", sub: skewTag },
    { label: "最高日", value: v.bestDay ? `${money(v.bestDay.value)}` : "—", kind: "money", sub: v.bestDay?.date || "" },
    { label: "最低日", value: v.worstDay ? `${money(v.worstDay.value)}` : "—", kind: "money", sub: v.worstDay?.date || "" },
  ];

  const p = v.percentiles || {};
  const pct = [
    { key: "P10", val: p.P10, color: "var(--celadon)" },
    { key: "P25", val: p.P25, color: "var(--celadon)" },
    { key: "P50", val: p.P50, color: "var(--gold)" },
    { key: "P75", val: p.P75, color: "var(--gold)" },
    { key: "P90", val: p.P90, color: "var(--carmine)" },
  ];
  const maxPct = Math.max(...pct.map((x) => x.val || 0), 1);

  const pctBars = pct.map((p) => `
    <div class="vol-pct">
      <span class="vol-pct-key">${p.key}</span>
      <div class="vol-pct-track"><div class="vol-pct-fill" style="width:${(p.val / maxPct) * 100}%; background:${p.color}"></div></div>
      <span class="vol-pct-val">${escapeHtml(money(p.val))}</span>
    </div>
  `).join("");

  const statCards = stats.map((s) => `
    <div class="vol-stat">
      <span class="vol-stat-label">${escapeHtml(s.label)}</span>
      <strong class="vol-stat-value" style="${s.color ? `color:${s.color}` : ""}">${escapeHtml(String(s.value))}</strong>
      ${s.sub ? `<span class="vol-stat-sub">${escapeHtml(s.sub)}</span>` : ""}
    </div>
  `).join("");

  els.volatility.innerHTML = `
    <div class="vol-grid">${statCards}</div>
    <div class="vol-pct-block">
      <span class="vol-pct-title">百分位数</span>
      ${pctBars}
    </div>
  `;
}

/* ============================================================
   LORENZ CURVE (ECharts)
   ============================================================ */
function renderLorenz(conc) {
  if (!conc || !conc.skus) {
    els.lorenzStats.innerHTML = "";
    disposeChart(els.lorenzChart);
    els.lorenzChart.innerHTML = empty("暂无数据");
    return;
  }
  const hhiTag = conc.hhi < 0.15 ? { label: "分散", color: "var(--celadon)" }
    : conc.hhi < 0.25 ? { label: "中等", color: "var(--gold)" }
    : { label: "集中", color: "var(--carmine)" };

  els.lorenzStats.innerHTML = `
    <div class="lz-card">
      <span>商品 SKU 数</span>
      <strong>${number(conc.skus)}</strong>
    </div>
    <div class="lz-card">
      <span>HHI 集中度</span>
      <strong style="color:${hhiTag.color}">${(conc.hhi * 10000).toFixed(0)}</strong>
      <em>${hhiTag.label}</em>
    </div>
    <div class="lz-card">
      <span>Top 5 SKU 占比</span>
      <strong>${(conc.top5Share * 100).toFixed(1)}%</strong>
    </div>
    <div class="lz-card">
      <span>Top 20 SKU 占比</span>
      <strong>${(conc.top20Share * 100).toFixed(1)}%</strong>
    </div>
  `;

  const chart = getOrCreateChart(els.lorenzChart);
  if (!chart) {
    renderLorenzFallback(conc);
    return;
  }

  const shares = conc.shares || [];
  const lorenzData = [[0, 0], ...shares.map((s) => [Math.round(s.q * 100), Math.round(s.share * 1000) / 10])];

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "item",
      ...ECHARTS_THEME.tooltip,
      formatter: (params) => {
        if (!params.data) return "";
        const [skuPct, revPct] = params.data;
        return `
          <div style="font-weight:600;margin-bottom:4px;color:#c89b3c;">洛伦兹集中度曲线</div>
          <div style="font-size:12px;color:#f5eee6;">前 <b>${skuPct}%</b> SKU 贡献了 <b>${revPct}%</b> 营业额</div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 20,
      bottom: 24,
      right: 24,
    },
    xAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLine: ECHARTS_THEME.axisLine,
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: "{value}%",
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLine: { show: false },
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: "{value}%",
      },
    },
    series: [
      {
        name: "完全平等线",
        type: "line",
        symbol: "none",
        lineStyle: { color: "rgba(255, 255, 255, 0.25)", width: 1.2, type: "dashed" },
        data: [[0, 0], [100, 100]],
        tooltip: { show: false },
      },
      {
        name: "实际集中度",
        type: "line",
        smooth: 0.25,
        symbol: "circle",
        symbolSize: 6,
        itemStyle: { color: "#c89b3c" },
        lineStyle: { width: 2.4, color: "#c89b3c" },
        areaStyle: {
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "rgba(200, 155, 60, 0.35)" },
                { offset: 1, color: "rgba(200, 155, 60, 0.05)" },
              ])
            : "rgba(200, 155, 60, 0.15)"),
        },
        data: lorenzData,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderLorenzFallback(conc) {
  const shares = conc.shares || [];
  const pts = [{ x: 0, y: 0 }];
  for (const s of shares) {
    pts.push({ x: s.q, y: s.share });
  }
  const width = 460;
  const height = 240;
  const pad = { left: 50, right: 18, top: 16, bottom: 32 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (v) => pad.left + v * innerW;
  const y = (v) => pad.top + innerH - v * innerH;

  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ");
  const areaPath = `${path} L${x(1)},${y(0)} L${x(0)},${y(0)} Z`;
  const eqLine = `M${x(0)},${y(0)} L${x(1)},${y(1)}`;

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const grid = ticks
    .map((t) => {
      const yy = pad.top + innerH - t * innerH;
      const xx = pad.left + t * innerW;
      return `<line class="grid-line" x1="${xx}" x2="${xx}" y1="${pad.top}" y2="${pad.top + innerH}" />
              <line class="grid-line" x1="${pad.left}" x2="${pad.left + innerW}" y1="${yy}" y2="${yy}" />`;
    })
    .join("");
  const yLabels = ticks.map((t) => `<text class="axis-label" x="${pad.left - 6}" y="${pad.top + innerH - t * innerH + 3}" text-anchor="end">${(t * 100).toFixed(0)}%</text>`).join("");
  const xLabels = ticks.map((t) => `<text class="x-label" x="${pad.left + t * innerW}" y="${height - 8}" text-anchor="middle">${(t * 100).toFixed(0)}%</text>`).join("");

  els.lorenzChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
      ${grid}
      ${yLabels}
      ${xLabels}
      <path d="${areaPath}" fill="#c89b3c" opacity="0.15" />
      <path d="${eqLine}" stroke="var(--muted-2)" stroke-dasharray="3 3" stroke-width="1.2" fill="none" />
      <path d="${path}" stroke="#c89b3c" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round" />
      ${pts.slice(1).map((p) => `<circle cx="${x(p.x)}" cy="${y(p.y)}" r="3.5" fill="#c89b3c"><title>前 ${(p.x * 100).toFixed(0)}% SKU 贡献 ${(p.y * 100).toFixed(1)}% 收入</title></circle>`).join("")}
      <text x="${width - 14}" y="${pad.top + 12}" class="axis-label" text-anchor="end" style="fill:var(--muted-2)">完全平等线</text>
    </svg>
  `;
}

function renderCategoryByHour(rows) {
  if (!rows || !rows.length) {
    els.catHourHeat.innerHTML = empty("暂无数据");
    return;
  }
  // Build pivot: rows of (收入分类, 小时, 实收金额)
  const categories = [...new Set(rows.map((r) => r["收入分类"]))];
  const hours = [...new Set(rows.map((r) => Number(r["小时"])))].sort((a, b) => a - b);
  const lookup = new Map();
  for (const r of rows) {
    lookup.set(`${r["收入分类"]}-${r["小时"]}`, Number(r["实收金额"]) || 0);
  }
  // The store does not operate in the early morning; start the heatmap at 10:00.
  const showHours = hours.filter((h) => h >= 10 && h <= 22);
  if (!showHours.length) {
    els.catHourHeat.innerHTML = empty("暂无 10:00 后的时段数据");
    return;
  }
  const max = Math.max(
    ...rows
      .filter((r) => Number(r["小时"]) >= 10 && Number(r["小时"]) <= 22)
      .map((r) => Number(r["实收金额"]) || 0),
    1,
  );
  const gridStyle = `grid-template-columns: minmax(48px, 54px) repeat(${showHours.length}, minmax(0, 1fr));`;

  function color(v) {
    if (v === 0) return "transparent";
    const t = v / max;
    return `rgba(91, 140, 123, ${(0.05 + t * 0.95).toFixed(3)})`;
  }

  const header = showHours.map((h) => `<div class="chh-hour-label">${h}</div>`).join("");
  const rowsHtml = categories
    .map((cat) => {
      const cells = showHours
        .map((h) => {
          const v = lookup.get(`${cat}-${h}`) || 0;
          return `<div class="chh-cell" style="background:${color(v)}" title="${escapeHtml(cat)} ${h}:00 · ${escapeHtml(money(v))}">
            ${v > 0 ? `<span class="chh-val">${escapeHtml(money(v).replace("¥", "¥"))}</span>` : ""}
          </div>`;
        })
        .join("");
      return `<div class="chh-row" style="${gridStyle}"><div class="chh-row-label">${escapeHtml(cat)}</div>${cells}</div>`;
    })
    .join("");

  els.catHourHeat.innerHTML = `
    <div class="chh-header" style="${gridStyle}"><div class="chh-row-label"></div>${header}</div>
    ${rowsHtml}
    <div class="hm-legend" style="margin-top:8px"><span>少</span><div class="hm-scale" style="background:linear-gradient(90deg, rgba(91,140,123,0.05), rgba(91,140,123,1));"></div><span>多</span></div>
  `;
}

function renderOrderAmountDist(rows) {
  if (!rows || !rows.length) {
    els.orderAmountDist.innerHTML = empty("暂无数据");
    return;
  }
  const max = Math.max(...rows.map((r) => Number(r["订单数"]) || 0), 1);
  els.orderAmountDist.innerHTML = rows
    .map((r) => {
      const n = Number(r["订单数"]) || 0;
      const pct = Number(r["占比"]) || 0;
      const width = Math.max(2, (n / max) * 100);
      return `
        <div class="oad-row">
          <span class="oad-label">${escapeHtml(r["区间"])}</span>
          <div class="oad-track"><div class="oad-fill" style="width:${width}%"></div></div>
          <span class="oad-count">${number(n)}</span>
          <span class="oad-pct">${(pct * 100).toFixed(1)}%</span>
        </div>
      `;
    })
    .join("");
}

function renderAbcSummary(rows) {
  if (!rows.length) {
    els.abcSummary.innerHTML = "";
    return;
  }
  const total = rows.length;
  const counts = { A: 0, B: 0, C: 0 };
  const revenue = { A: 0, B: 0, C: 0 };
  for (const r of rows) {
    const c = r["ABC分类"] || "C";
    counts[c] = (counts[c] || 0) + 1;
    revenue[c] = (revenue[c] || 0) + (Number(r["实收金额"]) || 0);
  }
  const totalRev = Object.values(revenue).reduce((a, b) => a + b, 0) || 1;
  els.abcSummary.innerHTML = ["A", "B", "C"]
    .map((c) => {
      const rev = revenue[c] || 0;
      return `
        <div class="abc-card abc-${c.toLowerCase()}">
          <span class="abc-label">${c} 类</span>
          <strong class="abc-count">${counts[c]}</strong>
          <span class="abc-sub">${((rev / totalRev) * 100).toFixed(1)}% 收入 · ${escapeHtml(money(rev))}</span>
        </div>
      `;
    })
    .join("");
}

function renderAbcTable(rows) {
  if (!rows.length) {
    els.abcTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  // Show top 20 of each A and B
  const head = rows.slice(0, 30);
  const cols = [
    { key: "商品名称", label: "商品" },
    { key: "实收金额", label: "实收", num: true, money: true },
    { key: "销售数量", label: "数量", num: true },
    { key: "累计占比", label: "累计占比", num: true, percent: true },
    { key: "ABC分类", label: "ABC", cat: true },
  ];
  const html = tableHtml(head, cols);
  // Add CSS class to the ABC category column
  const enhanced = html.replace(/<td class="cat cat-default">(A|B|C)<\/td>/g, (m, c) => {
    return `<td class="cat abc-tag abc-${c.toLowerCase()}">${c}</td>`;
  });
  els.abcTable.innerHTML = enhanced;
}

function renderSlowTable(rows) {
  if (!rows.length) {
    els.slowTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  const cols = [
    { key: "商品名称", label: "商品" },
    { key: "商品分类", label: "分类" },
    { key: "实收金额", label: "实收", num: true, money: true },
    { key: "销售数量", label: "数量", num: true },
    { key: "订单数", label: "订单", num: true },
  ];
  els.slowTable.innerHTML = tableHtml(rows, cols);
}

/* ============================================================
   RAW TABLE (per raw tab)
   ============================================================ */
function renderRawTable() {
  if (!state.payload) return;
  const map = {
    sales: state.payload.raw.sales,
    loss: state.payload.raw.loss,
    cards: state.payload.raw.cards,
    cardsDetail: state.payload.raw.cardsDetail,
    salesDetail: state.payload.raw.salesDetail,
  };
  const rows = map[state.activeRaw] || [];
  if (!rows.length) {
    els.rawTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  const columns = Object.keys(rows[0]);
  const cols = columns.map((c) => ({
    key: c,
    label: c,
    num: isMoneyKey(c),
    money: isMoneyKey(c),
  }));
  els.rawTable.innerHTML = tableHtml(rows, cols);
}

function isMoneyKey(key) {
  return ["实收金额", "商品总价", "报损金额", "损耗价值", "商品成本估算", "净利润估算", "客单价", "固定支出", "充值总金额", "储值卡充值", "储值卡消费", "储值卡消费总金额", "本金消费金额", "赠送消费金额", "充值金额", "赠送金额", "支付金额"].includes(key);
}

/* ============================================================
   TABLE HELPER
   ============================================================ */
function tableHtml(rows, columns, _opts = {}) {
  const header = columns
    .map((c) => `<th class="${c.num ? "num" : ""}">${escapeHtml(c.label)}</th>`)
    .join("");
  const body = rows
    .map((row) => {
      const tds = columns
        .map((c) => {
          const v = row[c.key];
          const cls = c.num ? "num" : "muted";
          if (v == null || v === "") return `<td class="${cls}">—</td>`;
          if (c.money) return `<td class="num">${escapeHtml(money(v))}</td>`;
          if (c.percent) return `<td class="num">${escapeHtml(percentFmt.format(Number(v) || 0))}</td>`;
          if (c.decimals) return `<td class="num">${escapeHtml(decimalNumberFmt.format(Number(v) || 0))}</td>`;
          if (c.cat) {
            const text = String(v);
            const key = text.toLowerCase();
            const catCls = ["bakery", "beverage", "meal"].includes(key) ? `cat-${key}` : "cat-default";
            return `<td class="cat ${catCls}">${escapeHtml(text)}</td>`;
          }
          return `<td class="${cls}">${escapeHtml(String(v))}</td>`;
        })
        .join("");
      return `<tr>${tds}</tr>`;
    })
    .join("");
  return `<thead><tr>${header}</tr></thead><tbody>${body}</tbody>`;
}

function emptyRow(message) {
  return `<tbody><tr><td colspan="1"><div class="empty">${escapeHtml(message)}</div></td></tr></tbody>`;
}

/* ============================================================
   UTILITIES
   ============================================================ */
function downloadJson() {
  if (!state.payload) return;
  const blob = new Blob([JSON.stringify(state.payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `pospal-dashboard-${state.payload.meta.year}-${String(state.payload.meta.month).padStart(2, "0")}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

/* ============================================================
   HUMEN WEATHER ARCHIVE
   ============================================================ */
function renderWeatherDaily(weather) {
  if (!els.weatherDaily) return;
  const latest = weather?.latest;
  const days = weather?.days || [];
  if (!weather || weather.status === "unavailable" || !latest || !days.length) {
    els.weatherDaily.innerHTML = `
      <div class="weather-today-empty">
        <span aria-hidden="true">☁</span>
        <div><strong>天气记录暂不可用</strong><p>${escapeHtml(weather?.message || "暂时无法获取门店天气，请稍后刷新。")}</p></div>
      </div>`;
    return;
  }

  const value = (numberValue, suffix) => numberValue == null
    ? "—"
    : `${Number(numberValue).toFixed(1)}${suffix}`;
  const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  });
  const dateLabel = dateFormatter.format(new Date(`${latest.date}T00:00:00`));
  const hasRain = Number(latest.precipitation || 0) >= 0.1;
  const historyRows = days.map((day) => `
    <article class="weather-history-row ${Number(day.precipitation || 0) >= 0.1 ? "is-rain" : "is-dry"}">
      <div class="weather-history-date">
        <strong>${escapeHtml(day.date)}</strong>
        <small>${escapeHtml(dateFormatter.format(new Date(`${day.date}T00:00:00`)))}</small>
      </div>
      <div class="weather-history-condition"><span aria-hidden="true">${escapeHtml(day.icon || "◌")}</span><div><strong>${escapeHtml(day.condition || "天气未知")}</strong><small>${escapeHtml(day.dataType || "天气数据")}</small></div></div>
      <div><span>最高 / 最低</span><strong>${value(day.temperatureMax, "°")} / ${value(day.temperatureMin, "°")}</strong></div>
      <div><span>降水</span><strong>${value(day.precipitation, " mm")}</strong></div>
      <div><span>最大风速</span><strong>${value(day.windSpeedMax, " km/h")}</strong></div>
      <div><span>日照</span><strong>${value(day.sunshineHours, " 小时")}</strong></div>
    </article>`).join("");

  els.weatherDaily.innerHTML = `
    <section class="weather-now-card ${hasRain ? "is-rain" : "is-dry"}">
      <header class="weather-now-head">
        <div>
          <span>${escapeHtml(weather.location || "示范城市 · 示范区")}</span>
          <strong>${escapeHtml(dateLabel)}</strong>
        </div>
        <small>${escapeHtml(weather.provider || "Open-Meteo")}</small>
      </header>
      <div class="weather-now-main">
        <span class="weather-now-icon" aria-hidden="true">${escapeHtml(latest.icon || "◌")}</span>
        <div class="weather-now-condition">
          <span>${latest.isToday ? "今日" : "最近记录"}</span>
          <h4>${escapeHtml(latest.condition || "天气未知")}</h4>
          <p>最高 ${value(latest.temperatureMax, "°")} · 最低 ${value(latest.temperatureMin, "°")}</p>
        </div>
      </div>
      <div class="weather-now-metrics">
        <div><span>平均温度</span><strong>${value(latest.temperatureMean, "°C")}</strong></div>
        <div><span>降水</span><strong>${value(latest.precipitation, " mm")}</strong><small>${value(latest.precipitationHours, " 小时")}</small></div>
        <div><span>最大风速</span><strong>${value(latest.windSpeedMax, " km/h")}</strong></div>
        <div><span>日照时长</span><strong>${value(latest.sunshineHours, " 小时")}</strong></div>
      </div>
      <footer class="weather-now-foot">
        <span>${escapeHtml(weather.message || "天气记录已更新")}</span>
        <span>${weather.fetchedAt ? `更新于 ${escapeHtml(weather.fetchedAt)}` : ""}</span>
      </footer>
    </section>
    <section class="weather-history">
      <header><div><span>DAILY ARCHIVE</span><h4>逐日天气</h4></div><strong>${number(days.length)} 天</strong></header>
      <div class="weather-history-list">${historyRows}</div>
    </section>`;
}

/* ============================================================
   WEATHER × SALES VISUALIZATIONS (ECharts)
   ============================================================ */
function computeWeatherSalesFromPayload(data) {
  const daily = data?.daily || [];
  const weatherDays = data?.weatherDaily?.days || [];
  if (!daily.length || !weatherDays.length) return null;

  const weatherMap = new Map();
  for (const w of weatherDays) {
    const dStr = String(w.date || "").slice(0, 10);
    if (dStr) weatherMap.set(dStr, w);
  }

  const timeline = [];
  const scatter = [];
  const table = [];
  const conditionMap = new Map();

  for (const d of daily) {
    const dStr = String(d["日期"] || "").slice(0, 10);
    const w = weatherMap.get(dStr);
    if (!w) continue;

    const rev = Number(d["实收金额"] || d["营业额"] || 0);
    const ord = Number(d["订单笔数"] || d["订单数"] || 0);
    const tkt = ord > 0 ? rev / ord : (Number(d["客单价"]) || 0);
    const precip = Number(w.precipitation || w.rain || 0);
    const tmax = Number(w.temperatureMax || w.temperatureMean || 0);
    const tmin = Number(w.temperatureMin || 0);
    const cond = String(w.condition || "晴");
    const icon = String(w.icon || "◌");
    const cat = String(w.category || "其他");

    const item = {
      date: dStr,
      condition: cond,
      category: cat,
      icon: icon,
      revenue: Math.round(rev * 100) / 100,
      orders: ord,
      ticket: Math.round(tkt * 100) / 100,
      tempMax: tmax,
      tempMin: tmin,
      precipitation: precip,
    };
    timeline.push(item);
    scatter.push(item);
    table.push({
      日期: dStr,
      天气: `${icon} ${cond}`,
      最高温: tmax,
      最低温: tmin,
      降水量: precip,
      实收金额: Math.round(rev * 100) / 100,
      订单数: ord,
      客单价: Math.round(tkt * 100) / 100,
    });

    if (!conditionMap.has(cond)) {
      conditionMap.set(cond, { condition: cond, category: cat, icon: icon, days: 0, totalRevenue: 0, totalOrders: 0 });
    }
    const cObj = conditionMap.get(cond);
    cObj.days += 1;
    cObj.totalRevenue += rev;
    cObj.totalOrders += ord;
  }

  if (!timeline.length) return null;

  timeline.sort((a, b) => a.date.localeCompare(b.date));
  table.sort((a, b) => a.日期.localeCompare(b.日期));

  const totalRev = timeline.reduce((s, t) => s + t.revenue, 0);
  const baselineAvgRev = timeline.length > 0 ? totalRev / timeline.length : 1;

  const byCondition = [...conditionMap.values()].map((c) => {
    const avgRev = c.days > 0 ? c.totalRevenue / c.days : 0;
    const avgOrd = c.days > 0 ? c.totalOrders / c.days : 0;
    const avgTkt = c.totalOrders > 0 ? c.totalRevenue / c.totalOrders : 0;
    const impactPct = baselineAvgRev > 0 ? Math.round(((avgRev - baselineAvgRev) / baselineAvgRev) * 1000) / 10 : 0;
    return {
      condition: c.condition,
      category: c.category,
      icon: c.icon,
      days: c.days,
      totalRevenue: Math.round(c.totalRevenue * 100) / 100,
      avgRevenue: Math.round(avgRev * 100) / 100,
      avgOrders: Math.round(avgOrd * 10) / 10,
      avgTicket: Math.round(avgTkt * 100) / 100,
      impactPct: impactPct,
    };
  });
  byCondition.sort((a, b) => b.avgRevenue - a.avgRevenue);

  const rainItems = timeline.filter((t) => t.precipitation >= 0.1 || t.condition.includes("雨"));
  const dryItems = timeline.filter((t) => t.precipitation < 0.1 && !t.condition.includes("雨"));

  const rainDays = rainItems.length;
  const dryDays = dryItems.length;
  const rainAvgRev = rainDays > 0 ? rainItems.reduce((s, t) => s + t.revenue, 0) / rainDays : 0;
  const dryAvgRev = dryDays > 0 ? dryItems.reduce((s, t) => s + t.revenue, 0) / dryDays : 0;
  const rainAvgOrd = rainDays > 0 ? rainItems.reduce((s, t) => s + t.orders, 0) / rainDays : 0;
  const dryAvgOrd = dryDays > 0 ? dryItems.reduce((s, t) => s + t.orders, 0) / dryDays : 0;
  const rainAvgTkt = rainItems.reduce((s, t) => s + t.orders, 0) > 0 ? rainItems.reduce((s, t) => s + t.revenue, 0) / rainItems.reduce((s, t) => s + t.orders, 0) : 0;
  const dryAvgTkt = dryItems.reduce((s, t) => s + t.orders, 0) > 0 ? dryItems.reduce((s, t) => s + t.revenue, 0) / dryItems.reduce((s, t) => s + t.orders, 0) : 0;

  const rainImpactPct = (dryAvgRev > 0 && rainDays > 0)
    ? Math.round(((rainAvgRev - dryAvgRev) / dryAvgRev) * 1000) / 10
    : 0;

  const summary = {
    totalDays: timeline.length,
    rainDays: rainDays,
    dryDays: dryDays,
    rainAvgRevenue: Math.round(rainAvgRev * 100) / 100,
    dryAvgRevenue: Math.round(dryAvgRev * 100) / 100,
    rainAvgOrders: Math.round(rainAvgOrd * 10) / 10,
    dryAvgOrders: Math.round(dryAvgOrd * 10) / 10,
    rainAvgTicket: Math.round(rainAvgTkt * 100) / 100,
    dryAvgTicket: Math.round(dryAvgTkt * 100) / 100,
    rainImpactPct: rainImpactPct,
    bestCondition: byCondition[0] || {},
    worstCondition: byCondition[byCondition.length - 1] || {},
    baselineAvgRevenue: Math.round(baselineAvgRev * 100) / 100,
  };

  return {
    status: "available",
    summary: summary,
    byCondition: byCondition,
    timeline: timeline,
    scatter: scatter,
    table: table,
  };
}

function renderWeatherSales(ws, data) {
  if (!els.weatherSalesSummary) return;

  let source = ws;
  if (!source || source.status === "unavailable" || !source.summary || !source.summary.totalDays) {
    source = computeWeatherSalesFromPayload(data);
  }

  if (!source || source.status === "unavailable" || !source.summary || !source.summary.totalDays) {
    els.weatherSalesSummary.innerHTML = empty("暂无天气与实收交叉分析数据");
    disposeChart(els.weatherSalesConditionChart);
    disposeChart(els.weatherSalesScatterChart);
    disposeChart(els.weatherSalesTimelineChart);
    if (els.weatherSalesTable) els.weatherSalesTable.innerHTML = emptyRow("暂无对照明细");
    return;
  }

  renderWeatherSalesSummary(source.summary);
  renderWeatherConditionChart(source.byCondition || []);
  renderWeatherScatterChart(source.scatter || []);
  renderWeatherTimelineChart(source.timeline || []);
  renderWeatherSalesTable(source.table || []);
}

function renderWeatherSalesSummary(summary) {
  if (!els.weatherSalesSummary) return;
  const s = summary || {};
  const rainPct = Number(s.rainImpactPct) || 0;
  const isRainNegative = rainPct < 0;
  const badgeCls = isRainNegative ? "neg" : (rainPct > 0 ? "pos" : "");
  const badgeText = `${rainPct > 0 ? "+" : ""}${rainPct.toFixed(1)}%`;

  const best = s.bestCondition || {};
  const rainDays = s.rainDays || 0;
  const dryDays = s.dryDays || 0;
  const rainAvg = Number(s.rainAvgRevenue) || 0;
  const dryAvg = Number(s.dryAvgRevenue) || 0;
  const rainOrders = Number(s.rainAvgOrders) || 0;
  const dryOrders = Number(s.dryAvgOrders) || 0;
  const rainTicket = Number(s.rainAvgTicket) || 0;
  const dryTicket = Number(s.dryAvgTicket) || 0;

  els.weatherSalesSummary.innerHTML = `
    <div class="ws-card ws-rain">
      <div class="ws-card-head">
        <span class="ws-card-label">雨天营收效应</span>
        <span class="ws-card-badge ${badgeCls}">${badgeText}</span>
      </div>
      <div class="ws-card-val">${escapeHtml(money(rainAvg))} <em>/ 雨天日均</em></div>
      <div class="ws-card-foot">
        降水日数 <strong>${rainDays} 天</strong>（非雨天日均 ${escapeHtml(money(dryAvg))} · <strong>${dryDays} 天</strong>）
      </div>
    </div>

    <div class="ws-card ws-sun">
      <div class="ws-card-head">
        <span class="ws-card-label">最吸金天气</span>
        <span class="ws-card-badge pos">${best.impactPct != null && best.impactPct > 0 ? `+${best.impactPct}%` : "最高"}</span>
      </div>
      <div class="ws-card-val">${escapeHtml(best.icon || "☀")} ${escapeHtml(best.condition || "晴朗")} <em>${escapeHtml(money(best.avgRevenue || 0))}</em></div>
      <div class="ws-card-foot">
        累计 <strong>${best.days || 0} 天</strong> · 日均 <strong>${best.avgOrders || 0} 单</strong>（客单 ${escapeHtml(money(best.avgTicket || 0))}）
      </div>
    </div>

    <div class="ws-card ws-orders">
      <div class="ws-card-head">
        <span class="ws-card-label">雨天客流与订单</span>
        <span class="ws-card-badge ${rainOrders < dryOrders ? "neg" : "pos"}">${dryOrders > 0 ? (((rainOrders - dryOrders) / dryOrders) * 100).toFixed(1) + "%" : "—"}</span>
      </div>
      <div class="ws-card-val">${rainOrders.toFixed(1)} <em>单 / 雨天日均</em></div>
      <div class="ws-card-foot">
        晴旱天日均 <strong>${dryOrders.toFixed(1)} 单</strong>（日均单量差 <strong>${(rainOrders - dryOrders).toFixed(1)} 单</strong>）
      </div>
    </div>

    <div class="ws-card ws-ticket">
      <div class="ws-card-head">
        <span class="ws-card-label">雨天客单价表现</span>
        <span class="ws-card-badge ${rainTicket >= dryTicket ? "pos" : "neg"}">${dryTicket > 0 ? (((rainTicket - dryTicket) / dryTicket) * 100).toFixed(1) + "%" : "—"}</span>
      </div>
      <div class="ws-card-val">${escapeHtml(money(rainTicket))} <em>/ 雨天客单</em></div>
      <div class="ws-card-foot">
        晴旱天客单 <strong>${escapeHtml(money(dryTicket))}</strong> · 对齐分析共 <strong>${s.totalDays || 0} 天</strong>
      </div>
    </div>
  `;
}

function renderWeatherConditionChart(byCondition) {
  if (!els.weatherSalesConditionChart) return;
  if (!byCondition || !byCondition.length) {
    disposeChart(els.weatherSalesConditionChart);
    els.weatherSalesConditionChart.innerHTML = empty("暂无数据");
    return;
  }

  const chart = getOrCreateChart(els.weatherSalesConditionChart);
  if (!chart) return;

  const xData = byCondition.map((c) => `${c.icon || "◌"} ${c.condition}`);
  const revValues = byCondition.map((c) => Number(c.avgRevenue) || 0);
  const ordValues = byCondition.map((c) => Number(c.avgOrders) || 0);

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: ECHARTS_THEME.axisPointer,
      formatter: (params) => {
        if (!params || !params.length) return "";
        const item = byCondition[params[0].dataIndex] || {};
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(item.icon || "")} ${escapeHtml(item.condition || "")}（${item.days || 0} 天）</div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#c89b3c;">● 日均实收</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(item.avgRevenue))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#5b8c7b;">● 日均订单</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${item.avgOrders} 单</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">● 平均客单价</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(item.avgTicket))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">● 晴天基准波动</span>
            <strong style="color:${item.impactPct >= 0 ? "#5b8c7b" : "#c44536"};font-family:'JetBrains Mono',monospace;">${item.impactPct >= 0 ? "+" : ""}${item.impactPct}%</strong>
          </div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 36,
      bottom: 28,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        interval: 0,
        rotate: byCondition.length > 5 ? 15 : 0,
      },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: "value",
        position: "left",
        name: "日均实收",
        nameTextStyle: { color: "#a89f91", fontSize: 10 },
        axisLine: { show: false },
        splitLine: ECHARTS_THEME.splitLine,
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => compactNumber(v),
        },
      },
      {
        type: "value",
        position: "right",
        name: "日均订单",
        nameTextStyle: { color: "#a89f91", fontSize: 10 },
        axisLine: { show: false },
        splitLine: { show: false },
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => `${v}单`,
        },
      },
    ],
    series: [
      {
        name: "日均实收",
        type: "bar",
        yAxisIndex: 0,
        barMaxWidth: 36,
        itemStyle: {
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "#c89b3c" },
                { offset: 1, color: "rgba(200, 155, 60, 0.25)" },
              ])
            : "#c89b3c"),
          borderRadius: [4, 4, 0, 0],
        },
        label: {
          show: true,
          position: "top",
          color: "#a89f91",
          fontSize: 10,
          fontFamily: '"JetBrains Mono", monospace',
          formatter: (p) => `${byCondition[p.dataIndex]?.days || 0}天`,
        },
        data: revValues,
      },
      {
        name: "日均订单",
        type: "line",
        yAxisIndex: 1,
        smooth: 0.3,
        showSymbol: true,
        symbolSize: 6,
        itemStyle: { color: "#5b8c7b" },
        lineStyle: { width: 2.2, color: "#5b8c7b" },
        data: ordValues,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderWeatherScatterChart(scatter) {
  if (!els.weatherSalesScatterChart) return;
  if (!scatter || !scatter.length) {
    disposeChart(els.weatherSalesScatterChart);
    els.weatherSalesScatterChart.innerHTML = empty("暂无数据");
    return;
  }

  const chart = getOrCreateChart(els.weatherSalesScatterChart);
  if (!chart) return;

  // Data point: [tempMax, revenue, orders, condition, icon, precipitation, date]
  const data = scatter.map((s) => [
    s.tempMax || 0,
    s.revenue || 0,
    s.orders || 0,
    s.condition || "",
    s.icon || "",
    s.precipitation || 0,
    s.date || "",
  ]);

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "item",
      ...ECHARTS_THEME.tooltip,
      formatter: (p) => {
        const [temp, rev, ord, cond, icon, precip, date] = p.data || [];
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(date)} (${escapeHtml(icon)} ${escapeHtml(cond)})</div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">营业实收</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(rev))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">最高气温</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${temp}°C</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">降水量</span>
            <strong style="color:#5b92b6;font-family:'JetBrains Mono',monospace;">${precip} mm</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">订单量</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${ord} 单</strong>
          </div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 32,
      bottom: 28,
      right: 24,
    },
    xAxis: {
      type: "value",
      name: "最高温(°C)",
      nameTextStyle: { color: "#a89f91", fontSize: 10 },
      axisLine: ECHARTS_THEME.axisLine,
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: "{value}°C",
      },
    },
    yAxis: {
      type: "value",
      name: "营业实收",
      nameTextStyle: { color: "#a89f91", fontSize: 10 },
      axisLine: { show: false },
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: (v) => compactNumber(v),
      },
    },
    series: [
      {
        name: "气象与实收",
        type: "scatter",
        symbolSize: (val) => Math.min(26, Math.max(9, (val[2] || 15) / 2.8)),
        itemStyle: {
          color: (p) => {
            const precip = p.data[5] || 0;
            const cond = p.data[3] || "";
            if (precip >= 0.1 || cond.includes("雨")) return "#5b92b6";
            if (cond.includes("阴") || cond.includes("云")) return "#8f7e91";
            return "#c89b3c";
          },
          opacity: 0.85,
          borderColor: "rgba(255, 255, 255, 0.2)",
          borderWidth: 1,
        },
        data: data,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderWeatherTimelineChart(timeline) {
  if (!els.weatherSalesTimelineChart) return;
  if (!timeline || !timeline.length) {
    disposeChart(els.weatherSalesTimelineChart);
    els.weatherSalesTimelineChart.innerHTML = empty("暂无数据");
    return;
  }

  const chart = getOrCreateChart(els.weatherSalesTimelineChart);
  if (!chart) return;

  const xData = timeline.map((t) => `${t.icon || "◌"} ${String(t.date).slice(5)}`);
  const revValues = timeline.map((t) => Number(t.revenue) || 0);
  const precipValues = timeline.map((t) => Number(t.precipitation) || 0);
  const tempValues = timeline.map((t) => Number(t.tempMax) || 0);

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: ECHARTS_THEME.axisPointer,
      formatter: (params) => {
        if (!params || !params.length) return "";
        const item = timeline[params[0].dataIndex] || {};
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(item.date)} (${escapeHtml(item.icon)} ${escapeHtml(item.condition)})</div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#c89b3c;">● 营业实收</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(item.revenue))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#5b92b6;">● 降水量</span>
            <strong style="color:#5b92b6;font-family:'JetBrains Mono',monospace;">${item.precipitation} mm</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#d36f31;">● 最高气温</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${item.tempMax}°C</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0;font-size:12px;">
            <span style="color:#a89f91;">● 订单笔数</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${number(item.orders)} 单</strong>
          </div>
        `;
      },
    },
    legend: {
      show: true,
      top: 0,
      right: 16,
      textStyle: { color: "#a89f91", fontSize: 11 },
      itemWidth: 14,
      itemHeight: 4,
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 36,
      bottom: timeline.length > 14 ? 46 : 28,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        interval: timeline.length > 20 ? "auto" : 0,
      },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: "value",
        position: "left",
        name: "营业实收",
        nameTextStyle: { color: "#a89f91", fontSize: 10 },
        axisLine: { show: false },
        splitLine: ECHARTS_THEME.splitLine,
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => compactNumber(v),
        },
      },
      {
        type: "value",
        position: "right",
        name: "降水/气温",
        nameTextStyle: { color: "#a89f91", fontSize: 10 },
        axisLine: { show: false },
        splitLine: { show: false },
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => `${v}`,
        },
      },
    ],
    dataZoom: timeline.length > 14 ? [
      {
        type: "slider",
        show: true,
        height: 14,
        bottom: 6,
        borderColor: "transparent",
        backgroundColor: "rgba(255,255,255,0.03)",
        fillerColor: "rgba(200,155,60,0.25)",
        handleStyle: { color: "#c89b3c" },
        textStyle: { color: "#a89f91", fontSize: 10 },
      },
      { type: "inside" },
    ] : [],
    series: [
      {
        name: "营业实收",
        type: "line",
        yAxisIndex: 0,
        smooth: 0.3,
        showSymbol: timeline.length <= 31,
        symbolSize: 6,
        itemStyle: { color: "#c89b3c" },
        lineStyle: { width: 2.4, color: "#c89b3c" },
        areaStyle: {
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "rgba(200, 155, 60, 0.3)" },
                { offset: 1, color: "rgba(200, 155, 60, 0.02)" },
              ])
            : "rgba(200, 155, 60, 0.15)"),
        },
        data: revValues,
      },
      {
        name: "降水量(mm)",
        type: "bar",
        yAxisIndex: 1,
        barMaxWidth: 14,
        itemStyle: {
          color: "rgba(91, 146, 182, 0.45)",
          borderRadius: [3, 3, 0, 0],
        },
        data: precipValues,
      },
      {
        name: "最高温(°C)",
        type: "line",
        yAxisIndex: 1,
        smooth: 0.2,
        showSymbol: false,
        lineStyle: { width: 1.5, color: "#d36f31", type: "dashed" },
        itemStyle: { color: "#d36f31" },
        data: tempValues,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderWeatherSalesTable(table) {
  if (!els.weatherSalesTable) return;
  if (!table || !table.length) {
    els.weatherSalesTable.innerHTML = emptyRow("暂无对照明细数据");
    return;
  }
  const cols = [
    { key: "日期", label: "日期" },
    { key: "天气", label: "天气状况" },
    { key: "最高温", label: "最高温(°C)", num: true },
    { key: "最低温", label: "最低温(°C)", num: true },
    { key: "降水量", label: "降水量(mm)", num: true },
    { key: "实收金额", label: "实收金额", num: true, money: true },
    { key: "订单数", label: "订单笔数", num: true },
    { key: "客单价", label: "客单价", num: true, money: true },
  ];
  els.weatherSalesTable.innerHTML = tableHtml(table, cols);
}

/* ============================================================
   DEEP POSPAL FIELD VISUALIZATIONS
   ============================================================ */

function renderPospalOverview(overview) {
  if (!overview || !overview.business) {
    els.pospalOverview.innerHTML = empty("暂无整体概况数据");
    return;
  }
  const b = overview.business || {};
  const online = overview.onlineStore || {};
  const events = overview.marketingCalendar || [];
  const sms = overview.smsBalance || {};
  const trend = overview.hourlyTrend || [];

  const primaryStats = [
    { label: "营业实收", value: money(b["营业实收"]), tone: "gold" },
    { label: "订单总数", value: number(b["订单总数"]), tone: "celadon" },
    { label: "客单价", value: decimalFmt.format(Number(b["客单价"]) || 0), tone: "neutral" },
    { label: "优惠金额", value: money(b["优惠金额"]), tone: "carmine" },
  ];
  const detailStats = [
    ["销售金额", money(b["销售金额"])],
    ["堂食单数", number(b["堂食单数"])],
    ["外卖单数", number(b["外卖单数"])],
    ["其他单数", number(b["其他单数"])],
    ["优惠单数", number(b["优惠单数"])],
    ["发券数量", number(b["发券数量"])],
    ["券付单数", number(b["券付单数"])],
  ];
  const onlineStats = [
    ["网店实收", money(online["网店实收"])],
    ["支付订单", number(online["支付订单"])],
    ["访客数量", online["访客数量"] == null ? "—" : number(online["访客数量"])],
    ["新增会员", number(online["新增会员"])],
  ];

  els.pospalOverview.innerHTML = `
    <div class="po-layout">
      <section class="po-main">
        <div class="po-tabs">
          <span class="active">今日</span><span>昨日</span><span>本周</span><span>本月</span>
        </div>
        <div class="po-primary">
          ${primaryStats.map((s) => `
            <div class="po-primary-card ${s.tone}">
              <span>${escapeHtml(s.label)}</span>
              <strong>${escapeHtml(s.value)}</strong>
            </div>
          `).join("")}
        </div>
        <div class="po-section-title">营业</div>
        <div class="po-detail-grid">
          ${detailStats.map(([label, value]) => `
            <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
          `).join("")}
        </div>
        <div class="po-section-title">网店</div>
        <div class="po-detail-grid online">
          ${onlineStats.map(([label, value]) => `
            <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
          `).join("")}
        </div>
        <div class="po-trend-head">
          <span><i class="gold"></i>营业额趋势图</span>
          <span><i class="celadon"></i>订单数趋势图</span>
        </div>
        <div class="po-trend">
          <div id="po-trend-chart" style="width:100%;height:180px;"></div>
        </div>
      </section>
      <aside class="po-side">
        <section class="po-calendar">
          <h4>营销日历</h4>
          <div class="po-events">
            ${events.map((e) => `
              <div class="po-event ${e.status === "past" ? "past" : ""}">
                <span>${escapeHtml(e["日期"])}</span>
                <strong>剩 <b>${escapeHtml(e["剩余天数"] >= 0 ? e["剩余天数"] : 0)}</b> 天</strong>
                <em>${escapeHtml(e["名称"])}</em>
              </div>
            `).join("") || empty("暂无营销日历")}
          </div>
        </section>
        <section class="po-sms">
          <span>短信余额(条)</span>
          <strong>${sms["余额条数"] == null ? "—" : number(sms["余额条数"])}</strong>
          <em>${escapeHtml(sms.message || "余额提醒")}</em>
        </section>
      </aside>
    </div>
  `;

  if (!trend.length) return;
  const trendDom = els.pospalOverview.querySelector("#po-trend-chart");
  if (!trendDom) return;

  const chart = getOrCreateChart(trendDom);
  if (!chart) {
    renderPospalOverviewFallback(trendDom, trend);
    return;
  }

  const xData = trend.map((r) => `${String(r["小时"]).padStart(2, "0")}:00`);
  const revValues = trend.map((r) => Number(r["营业额"]) || 0);
  const ordValues = trend.map((r) => Number(r["订单数"]) || 0);

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "axis",
      ...ECHARTS_THEME.tooltip,
      axisPointer: ECHARTS_THEME.axisPointer,
      formatter: (params) => {
        if (!params || !params.length) return "";
        const hour = params[0].axisValueLabel;
        const rev = params[0]?.value || 0;
        const ord = params[1]?.value || 0;
        return `
          <div style="font-weight:600;margin-bottom:6px;color:#c89b3c;font-family:'JetBrains Mono',monospace;">${escapeHtml(hour)} 时段</div>
          <div style="display:flex;justify-content:space-between;gap:18px;font-size:12px;">
            <span style="color:#c89b3c;">● 营业额</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${escapeHtml(money(rev))}</strong>
          </div>
          <div style="display:flex;justify-content:space-between;gap:18px;font-size:12px;">
            <span style="color:#5b8c7b;">● 订单数</span>
            <strong style="color:#f5eee6;font-family:'JetBrains Mono',monospace;">${number(ord)} 单</strong>
          </div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 24,
      bottom: 24,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLine: ECHARTS_THEME.axisLine,
      axisLabel: ECHARTS_THEME.axisLabel,
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: "value",
        position: "left",
        axisLine: { show: false },
        splitLine: ECHARTS_THEME.splitLine,
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => compactNumber(v),
        },
      },
      {
        type: "value",
        position: "right",
        axisLine: { show: false },
        splitLine: { show: false },
        axisLabel: {
          ...ECHARTS_THEME.axisLabel,
          formatter: (v) => `${v}单`,
        },
      },
    ],
    series: [
      {
        name: "营业额",
        type: "line",
        yAxisIndex: 0,
        smooth: 0.3,
        showSymbol: true,
        symbolSize: 5,
        itemStyle: { color: "#c89b3c" },
        lineStyle: { width: 2, color: "#c89b3c" },
        areaStyle: {
          color: (window.echarts?.graphic?.LinearGradient
            ? new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "rgba(200, 155, 60, 0.25)" },
                { offset: 1, color: "rgba(200, 155, 60, 0.02)" },
              ])
            : "rgba(200, 155, 60, 0.1)"),
        },
        data: revValues,
      },
      {
        name: "订单数",
        type: "line",
        yAxisIndex: 1,
        smooth: 0.3,
        showSymbol: true,
        symbolSize: 5,
        itemStyle: { color: "#5b8c7b" },
        lineStyle: { width: 2, color: "#5b8c7b" },
        data: ordValues,
      },
    ],
  };

  chart.setOption(option, true);
}

function renderPospalOverviewFallback(target, trend) {
  const maxRevenue = Math.max(...trend.map((r) => Number(r["营业额"]) || 0), 1);
  const maxOrders = Math.max(...trend.map((r) => Number(r["订单数"]) || 0), 1);
  const width = 680;
  const height = 180;
  const pad = { l: 42, r: 34, t: 20, b: 30 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const x = (i) => pad.l + (trend.length <= 1 ? innerW / 2 : (i / (trend.length - 1)) * innerW);
  const yRevenue = (v) => pad.t + innerH - ((Number(v) || 0) / maxRevenue) * innerH;
  const yOrders = (v) => pad.t + innerH - ((Number(v) || 0) / maxOrders) * innerH;
  const line = (key, yFn) => trend.map((r, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${yFn(r[key]).toFixed(1)}`).join(" ");
  target.innerHTML = `
    <svg class="po-trend-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="营业额与订单趋势">
      <line x1="${pad.l}" y1="${pad.t + innerH}" x2="${width - pad.r}" y2="${pad.t + innerH}" stroke="var(--line-soft)" />
      <path d="${line("营业额", yRevenue)}" fill="none" stroke="var(--gold)" stroke-width="2.4" vector-effect="non-scaling-stroke" />
      <path d="${line("订单数", yOrders)}" fill="none" stroke="var(--celadon)" stroke-width="2.4" vector-effect="non-scaling-stroke" />
      ${trend.map((r, i) => `
        <circle cx="${x(i).toFixed(1)}" cy="${yRevenue(r["营业额"]).toFixed(1)}" r="3" fill="var(--gold)" />
        <text x="${x(i).toFixed(1)}" y="${height - 8}" fill="var(--muted)" font-size="10" text-anchor="middle">${String(r["小时"]).padStart(2, "0")}</text>
      `).join("")}
    </svg>
  `;
}

function renderOpenClose(oc) {
  if (!oc || !oc.isOpen) {
    els.openClose.innerHTML = empty("暂无营业数据");
    return;
  }
  const fmtMin = (mins) => {
    if (!mins) return "—";
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h && m) return `${h}h ${m}m`;
    if (h) return `${h}h`;
    return `${m}m`;
  };
  const stages = [
    { key: "open", label: "开张", hour: oc.openHour, color: "var(--celadon)" },
    { key: "peak", label: "高峰", hour: oc.peakHour, color: "var(--gold)" },
    { key: "close", label: "打烊", hour: oc.closeHour, color: "var(--carmine)" },
  ];
  const stageHtml = stages.map((s) => `
    <div class="oc-stage">
      <span class="oc-dot" style="background:${s.color}"></span>
      <div>
        <span class="oc-stage-label">${escapeHtml(s.label)}</span>
        <strong class="oc-stage-time">${String(s.hour).padStart(2, "0")}:00</strong>
      </div>
    </div>
  `).join("");

  // Build a SVG "day shape" timeline
  const width = 460;
  const height = 80;
  const padX = 16;
  const padY = 12;
  const innerW = width - padX * 2;
  const startH = oc.openHour;
  const endH = Math.max(oc.closeHour, startH + 1);
  const peakH = oc.peakHour;
  const x = (h) => padX + ((h - startH) / (endH - startH)) * innerW;
  // Synthetic "intensity" curve: bell around peak
  function intensity(h) {
    const sigma = Math.max(1, (endH - startH) / 5);
    return Math.exp(-((h - peakH) ** 2) / (2 * sigma * sigma));
  }
  const segments = [];
  for (let h = startH; h < endH; h += 1) {
    const i = intensity(h + 0.5);
    segments.push(`<rect x="${x(h)}" y="${padY + (1 - i) * (height - padY * 2)}" width="${Math.max(2, x(h + 1) - x(h) - 1)}" height="${i * (height - padY * 2)}" rx="2" fill="var(--gold)" opacity="${(0.2 + i * 0.7).toFixed(2)}" />`);
  }
  // Markers for open / peak / close
  const markers = [
    { h: startH, label: "开", color: "var(--celadon)" },
    { h: peakH, label: "峰", color: "var(--gold)" },
    { h: endH, label: "收", color: "var(--carmine)" },
  ];
  const markerHtml = markers.map((m) => `
    <line x1="${x(m.h)}" x2="${x(m.h)}" y1="${padY - 4}" y2="${height - padY + 4}" stroke="${m.color}" stroke-width="1.2" stroke-dasharray="2 2" />
    <text x="${x(m.h)}" y="${height - 1}" font-size="9" fill="${m.color}" text-anchor="middle" font-family="JetBrains Mono, monospace">${m.label}</text>
  `).join("");

  els.openClose.innerHTML = `
    <div class="oc-stages">${stageHtml}</div>
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" class="oc-timeline">
      ${segments.join("")}
      ${markerHtml}
    </svg>
    <div class="oc-metrics">
      <div><span>爬坡</span><strong>${fmtMin(oc.ramp)}</strong></div>
      <div><span>收尾</span><strong>${fmtMin(oc.wind)}</strong></div>
      <div><span>首笔</span><strong>${escapeHtml(money(oc.openAmount))}</strong></div>
      <div><span>末笔</span><strong>${escapeHtml(money(oc.closeAmount))}</strong></div>
    </div>
  `;
}

function renderCalendar(rows) {
  if (!rows || !rows.length) {
    els.calendarGrid.innerHTML = empty("暂无日历数据");
    return;
  }
  // Find max revenue for color scaling
  const revenues = rows.map((r) => Number(r["实收金额"]) || 0);
  const maxRev = Math.max(...revenues, 1);

  // Group by week-of-month (Mon-Sun)
  const dayMap = new Map();
  for (const r of rows) {
    const d = new Date(r["日期"]);
    const dow = (d.getDay() + 6) % 7; // Mon=0 ... Sun=6
    if (!dayMap.has(d.getDate())) dayMap.set(d.getDate(), { date: d, data: r, dow });
  }
  // Find first day of month and pad leading empty cells
  const firstDate = new Date(rows[0]["日期"]);
  const firstDow = (firstDate.getDay() + 6) % 7;
  const cells = [];
  for (let i = 0; i < firstDow; i += 1) {
    cells.push({ empty: true });
  }
  // Iterate days in order
  const sortedDays = [...dayMap.keys()].sort((a, b) => a - b);
  for (const d of sortedDays) {
    const entry = dayMap.get(d);
    cells.push({ date: entry.date, data: entry.data, dow: entry.dow });
  }
  // Pad trailing empty cells to fill 6 rows
  while (cells.length < 42) cells.push({ empty: true });

  function color(v) {
    if (!v) return "transparent";
    const t = v / maxRev;
    return `rgba(200, 155, 60, ${(0.06 + t * 0.85).toFixed(3)})`;
  }

  const cellHtml = cells.map((c) => {
    if (c.empty) return `<div class="cal-cell empty"></div>`;
    const r = c.data;
    const rev = Number(r["实收金额"]) || 0;
    const profit = Number(r["净利润"]) || 0;
    const status = r["状态"] || "ok";
    return `
      <div class="cal-cell ${status}" style="background:${color(rev)}" title="${escapeHtml(String(r["日期"]))} · ${escapeHtml(money(rev))} · 利润 ${escapeHtml(money(profit))}">
        <span class="cal-day">${c.date.getDate()}</span>
        <span class="cal-val">${rev > 0 ? escapeHtml(compactMoney(rev)) : ""}</span>
        ${status === "loss" ? '<span class="cal-tag">亏</span>' : status === "warn" ? '<span class="cal-tag warn">!</span>' : ""}
      </div>
    `;
  }).join("");

  const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
  const headHtml = weekdays.map((d) => `<div class="cal-head">${d}</div>`).join("");

  els.calendarGrid.innerHTML = `
    <div class="cal-grid">${headHtml}${cellHtml}</div>
  `;
}

function renderDiscounts(d) {
  if (!d) {
    els.discounts.innerHTML = empty("暂无数据");
    return;
  }
  const dr = d["优惠率"] || 0;
  const drTag = dr < 0.05 ? { label: "低", color: "var(--celadon)" }
    : dr < 0.15 ? { label: "中等", color: "var(--gold)" }
    : { label: "高", color: "var(--carmine)" };

  // Discount bar
  const totalDisc = d["优惠金额"] || 0;
  const totalRev = d["实收金额"] || 0;
  const totalOrig = d["销售金额"] || 0;
  const maxBar = Math.max(totalOrig, totalRev, 1);

  els.discounts.innerHTML = `
    <div class="disc-stats">
      <div class="disc-stat">
        <span>销售金额</span>
        <strong>${escapeHtml(money(d["销售金额"]))}</strong>
      </div>
      <div class="disc-stat">
        <span>实收金额</span>
        <strong>${escapeHtml(money(d["实收金额"]))}</strong>
      </div>
      <div class="disc-stat highlight">
        <span>优惠金额</span>
        <strong>${escapeHtml(money(d["优惠金额"]))}</strong>
      </div>
      <div class="disc-stat">
        <span>优惠率</span>
        <strong style="color:${drTag.color}">${escapeHtml(percentFmt.format(dr))} <em>${drTag.label}</em></strong>
      </div>
      <div class="disc-stat">
        <span>优惠单数</span>
        <strong>${number(d["优惠单数"])} / ${number(d["订单总数"])} <em>${escapeHtml(percentFmt.format(d["优惠单占比"] || 0))}</em></strong>
      </div>
    </div>
    <div class="disc-bar">
      <div class="disc-bar-rev" style="width:${(totalRev / maxBar) * 100}%; background: linear-gradient(90deg, var(--celadon), var(--gold))"></div>
      <div class="disc-bar-orig" style="width:${((totalOrig - totalRev) / maxBar) * 100}%; background: var(--carmine); opacity: 0.6"></div>
    </div>
    <div class="disc-legend">
      <span><i style="background:linear-gradient(90deg, var(--celadon), var(--gold))"></i>实收</span>
      <span><i style="background:var(--carmine)"></i>优惠（折让）</span>
    </div>
  `;
}

function renderPaymentMix(pm) {
  if (!pm || !pm.methods || !pm.methods.length) {
    const expected = Number(pm?.expectedRevenue) || 0;
    els.paymentMix.innerHTML = `
      <div class="payment-empty">
        <span class="payment-empty-code">PAYMENT FIELD</span>
        <strong>支付方式字段尚未返回</strong>
        <p>${escapeHtml(pm?.message || "当前银豹接口结果没有可汇总的支付方式字段。")}</p>
        ${expected ? `<span>本期营业实收 ${escapeHtml(money(expected))}，接入支付明细后会自动核对。</span>` : ""}
      </div>
    `;
    return;
  }
  const total = pm.total || pm.methods.reduce((s, m) => s + (m["金额"] || 0), 0) || 1;
  const max = Math.max(...pm.methods.map((m) => Number(m["金额"]) || 0), 1);
  const colorMap = {
    "微信/支付宝": PALETTE.profit,
    "微信": PALETTE.profit,
    "支付宝": PALETTE.profit,
    "银豹付": PALETTE.profit,
    "美团": "#B86432",
    "饿了么": PALETTE.revenue,
    "抖音": PALETTE.card,
    "外卖": PALETTE.loss,
    "小程序": PALETTE.profit,
    "储值卡": PALETTE.card,
    "现金": PALETTE.revenue,
  };
  const gap = Number(pm.reconciliationGap) || 0;
  const coverage = pm.coverage == null ? null : Number(pm.coverage);
  const auditClass = pm.reconciled ? "ok" : "warn";
  const auditLabel = pm.reconciled ? "账款一致" : "待核对";
  const rows = pm.methods.map((m) => {
    const color = colorMap[m["支付方式"]] || "var(--celadon)";
    const pct = Math.max(2, (m["金额"] / max) * 100);
    return `
      <div class="pay-row">
        <span class="pay-name">
          <i style="background:${color}"></i>
          <span>
            <b>${escapeHtml(m["支付方式"])}</b>
            <small>${number(m["订单数"] || m["支付笔数"] || 0)} 单 · 均 ${escapeHtml(money(m["平均每单"] || 0))}</small>
          </span>
        </span>
        <div class="pay-track"><div class="pay-fill" style="width:${pct}%; background:${color}"></div></div>
        <span class="pay-amt">${escapeHtml(money(m["金额"]))}</span>
        <span class="pay-pct">${escapeHtml(percentFmt.format(m["占比"] || 0))}</span>
      </div>
    `;
  }).join("");
  els.paymentMix.innerHTML = `
    <div class="payment-ledger-head">
      <div>
        <span>接口支付总额</span>
        <strong>${escapeHtml(money(total))}</strong>
      </div>
      <div>
        <span>主支付方式</span>
        <strong>${escapeHtml(pm.dominantMethod || "—")} <em>${escapeHtml(percentFmt.format(pm.dominantShare || 0))}</em></strong>
      </div>
    </div>
    <div class="payment-audit ${auditClass}">
      <span class="payment-audit-state">${auditLabel}</span>
      <span>覆盖 ${number(pm.orderCount || 0)} 单</span>
      <span>${number(pm.paymentCount || 0)} 笔支付</span>
      <span>${number(pm.mixedPaymentOrders || 0)} 单混合支付</span>
      <strong>差额 ${escapeHtml(money(gap))}</strong>
      ${coverage !== null && Number.isFinite(coverage) ? `<em>覆盖率 ${escapeHtml(percentFmt.format(coverage))}</em>` : ""}
    </div>
    <div class="payment-methods">${rows}</div>
  `;
}

function renderTicketType(ticketType) {
  const types = ticketType?.types || [];
  els.ticketType.classList.toggle("hidden", !types.length);
  if (!types.length) {
    els.ticketType.innerHTML = "";
    return;
  }
  const totalOrders = types.reduce((sum, item) => sum + (Number(item["单数"]) || 0), 0) || 1;
  els.ticketType.innerHTML = `
    <div class="ticket-type-head">
      <span>单据构成</span>
      <em>${number(totalOrders)} 单</em>
    </div>
    <div class="ticket-type-list">
      ${types.map((item) => `
        <div class="ticket-type-chip">
          <span>${escapeHtml(item["类型"] || "未分类")}</span>
          <strong>${number(item["单数"] || 0)}</strong>
          <em>${escapeHtml(percentFmt.format((Number(item["单数"]) || 0) / totalOrders))}</em>
        </div>
      `).join("")}
    </div>
  `;
}

function renderMemberSummary(ms, balance = {}) {
  if (!ms) {
    els.memberSummary.innerHTML = empty("暂无会员数据");
    return;
  }
  const ratio = Number(balance?.["本金赠送比"]) || 0;
  const principal = Number(balance?.["本金消费"]) || 0;
  const gift = Number(balance?.["赠送消费"]) || 0;
  const items = [
    { label: "会员数", value: number(ms["会员数"]), color: "var(--gold)" },
    { label: "卡内剩余", value: money(ms["剩余金额"]), color: "var(--celadon)" },
    { label: "本月充值", value: money(ms["充值金额"]), color: "var(--plum)" },
    { label: "本月赠送", value: money(ms["赠送金额"]), color: "var(--carmine)" },
  ];
  els.memberSummary.innerHTML = `
    <div class="ms-grid">
      ${items.map((k) => `
        <div class="ms-cell">
          <span>${escapeHtml(k.label)}</span>
          <strong style="color:${k.color}">${escapeHtml(k.value)}</strong>
        </div>
      `).join("")}
    </div>
    <div class="ms-consumption">
      <span><i style="background:var(--celadon)"></i>本金消费 <strong>${escapeHtml(money(principal))}</strong></span>
      <span><i style="background:var(--plum)"></i>赠送消费 <strong>${escapeHtml(money(gift))}</strong></span>
    </div>
    <div class="ms-ratio">
      <span>本金消费 / 赠送消费</span>
      <strong>${ratio ? ratio.toFixed(1) : "—"} <em>${ratio >= 1 ? "健康" : "赠送信用偏多"}</em></strong>
    </div>
  `;
}

function renderProfitRanking(rows) {
  if (!rows || !rows.length) {
    els.profitRanking.innerHTML = empty("暂无利润数据");
    return;
  }
  // If 利润 column missing/zero, fall back to cost-derived profit
  const top = [...rows].slice(0, 10);
  const bottom = [...rows].slice(-5).reverse();
  const max = Math.max(...rows.map((r) => Math.abs(Number(r["利润"]) || 0)), 1);

  function row(r, i, side) {
    const profit = Number(r["利润"]) || 0;
    const margin = Number(r["利润率"]) || 0;
    const cls = profit < 0 ? "neg" : (margin < 0.2 ? "low" : "ok");
    return `
      <div class="pr-row ${cls}">
        <span class="pr-rank">${i + 1}</span>
        <span class="pr-name">${escapeHtml(r["商品名称"] || "—")}</span>
        <div class="pr-track"><div class="pr-fill ${cls}" style="width:${(Math.abs(profit) / max) * 100}%"></div></div>
        <span class="pr-profit">${escapeHtml(money(profit))}</span>
        <span class="pr-margin">${(margin * 100).toFixed(1)}%</span>
      </div>
    `;
  }
  const topHtml = top.map((r, i) => row(r, i, "top")).join("");
  const bottomHtml = bottom.map((r, i) => row(r, i, "bottom")).join("");

  els.profitRanking.innerHTML = `
    <div class="pr-block">
      <div class="pr-block-title">Top 10 利润王</div>
      ${topHtml}
    </div>
    <div class="pr-block">
      <div class="pr-block-title">Bottom 5 亏损品</div>
      ${bottomHtml}
    </div>
  `;
}

/* ============================================================
   PRODUCT BCG MATRIX (SCATTER & QUADRANT)
   ============================================================ */
function renderProductBCG(topProducts, profitByProduct, slowMovers, productABC) {
  if (!els.productBcgChart) return;
  if (!topProducts || !topProducts.length) {
    disposeChart(els.productBcgChart);
    els.productBcgChart.innerHTML = empty("暂无商品数据");
    return;
  }
  const chart = getOrCreateChart(els.productBcgChart);
  if (!chart) return;

  const profitMap = new Map();
  (profitByProduct || []).forEach((p) => {
    profitMap.set(p["商品名称"], {
      margin: Number(p["利润率"]) || (Number(p["实收金额"]) > 0 ? (Number(p["利润"]) || 0) / Number(p["实收金额"]) : 0.65),
      profit: Number(p["利润"]) || 0,
    });
  });

  const slowSet = new Set((slowMovers || []).map((s) => s["商品名称"]));
  const abcMap = new Map((productABC || []).map((a) => [a["商品名称"], a["ABC分类"]]));

  const items = topProducts.slice(0, 45).map((p) => {
    const name = p["商品名称"] || "";
    const qty = Number(p["销售数量"]) || 0;
    const rev = Number(p["实收金额"]) || 0;
    const cat = p["商品分类"] || p["收入分类"] || "烘焙";
    const profitInfo = profitMap.get(name) || { margin: 0.65, profit: rev * 0.65 };
    const margin = Math.min(Math.max(profitInfo.margin, 0), 1);
    const abc = abcMap.get(name) || "B";
    const isSlow = slowSet.has(name);
    return { name, qty, rev, cat, margin, profit: profitInfo.profit, abc, isSlow };
  });

  const sortedQty = [...items].map((i) => i.qty).sort((a, b) => a - b);
  const sortedMargin = [...items].map((i) => i.margin).sort((a, b) => a - b);
  const midQty = sortedQty[Math.floor(sortedQty.length / 2)] || 100;
  const midMargin = sortedMargin[Math.floor(sortedMargin.length / 2)] || 0.6;
  const maxRev = Math.max(...items.map((i) => i.rev), 1000);

  const seriesData = items.map((item) => {
    let quadName = "";
    let color = "";
    let action = "";
    if (item.qty >= midQty && item.margin >= midMargin) {
      quadName = "🌟 明星爆款";
      color = "#98651A";
      action = "主力盈利单品，确保原料充足与黄金展位";
    } else if (item.qty < midQty && item.margin >= midMargin) {
      quadName = "💡 暴利潜力";
      color = "#3F755F";
      action = "毛利极高但走量偏低，建议强化试吃与推荐话术";
    } else if (item.qty >= midQty && item.margin < midMargin) {
      quadName = "🧲 流量引流";
      color = "#76526F";
      action = "走量大但毛利偏低，建议与高毛利饮品/甜点组合连带";
    } else {
      quadName = "⚠️ 滞销淘汰";
      color = "#A84C3A";
      action = "低销低利，建议缩减烘焙批次或直接下架停产";
    }

    return {
      name: item.name,
      value: [item.qty, Math.round(item.margin * 1000) / 10, item.rev, item.cat, quadName, action, item.profit],
      itemStyle: {
        color: color,
        borderColor: "rgba(255, 255, 255, 0.4)",
        borderWidth: 1.5,
        shadowBlur: 6,
        shadowColor: color + "40",
      },
    };
  });

  const option = {
    animationDuration: 600,
    tooltip: {
      trigger: "item",
      ...ECHARTS_THEME.tooltip,
      formatter: (params) => {
        const d = params.value;
        const name = params.name;
        if (!Array.isArray(d)) return name;
        const [qty, marginPct, rev, cat, quadName, action, profit] = d;
        return `
          <div style="font-weight:700;font-size:14px;color:#c89b3c;margin-bottom:6px;font-family:'Fraunces',serif;">
            ${escapeHtml(name)} <span style="font-size:11px;font-weight:400;color:#a89f91;">(${escapeHtml(cat)})</span>
          </div>
          <div style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-bottom:8px;background:rgba(200,155,60,0.15);color:#f5eee6;">
            ${escapeHtml(quadName)}
          </div>
          <div style="font-size:12px;display:grid;grid-template-columns:auto auto;gap:4px 16px;margin-bottom:8px;font-family:'JetBrains Mono',monospace;">
            <span style="color:#a89f91;">销售数量:</span><strong style="color:#f5eee6;text-align:right;">${number(qty)} 件</strong>
            <span style="color:#a89f91;">单品毛利率:</span><strong style="color:#f5eee6;text-align:right;">${marginPct}%</strong>
            <span style="color:#a89f91;">实收金额:</span><strong style="color:#f5eee6;text-align:right;">${money(rev)}</strong>
            <span style="color:#a89f91;">估算利润:</span><strong style="color:#f5eee6;text-align:right;">${money(profit)}</strong>
          </div>
          <div style="border-top:1px dashed rgba(255,255,255,0.1);padding-top:6px;font-size:11px;color:#c89b3c;line-height:1.4;">
            💡 <strong>运营建议:</strong> ${escapeHtml(action)}
          </div>
        `;
      },
    },
    grid: {
      ...ECHARTS_THEME.grid,
      top: 36,
      left: 24,
      right: 48,
      bottom: 36,
    },
    xAxis: {
      name: "销量 (件)",
      nameLocation: "end",
      nameTextStyle: { color: "#a89f91", fontSize: 11 },
      type: "value",
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: ECHARTS_THEME.axisLabel,
    },
    yAxis: {
      name: "毛利率 (%)",
      nameLocation: "end",
      nameTextStyle: { color: "#a89f91", fontSize: 11 },
      type: "value",
      splitLine: ECHARTS_THEME.splitLine,
      axisLabel: {
        ...ECHARTS_THEME.axisLabel,
        formatter: (v) => `${v}%`,
      },
    },
    series: [
      {
        type: "scatter",
        symbolSize: (val) => {
          const r = val[2] || 0;
          return Math.max(14, Math.min(48, Math.sqrt(r / maxRev) * 48));
        },
        data: seriesData,
        markLine: {
          silent: true,
          lineStyle: { color: "rgba(200, 155, 60, 0.4)", type: "dashed", width: 1.2 },
          data: [
            { xAxis: midQty, label: { formatter: "中位数销量", color: "#a89f91", fontSize: 10 } },
            { yAxis: Math.round(midMargin * 100), label: { formatter: "中位数毛利", color: "#a89f91", fontSize: 10 } },
          ],
        },
      },
    ],
  };

  chart.setOption(option, true);
}

function renderLossReasonTable(d) {
  if (!d || !d.reasons || !d.reasons.length) {
    els.lossReasonTable.innerHTML = emptyRow("暂无数据");
    return;
  }
  const cols = [
    { key: "报损原因", label: "报损原因" },
    { key: "报废数量", label: "数量", num: true },
    { key: "报损金额", label: "金额", num: true, money: true },
  ];
  els.lossReasonTable.innerHTML = tableHtml(d.reasons, cols);
}

function compactMoney(v) {
  const n = Number(v) || 0;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  if (n >= 1000) return `${Math.round(n / 100) / 10}k`;
  return String(Math.round(n));
}

function empty(message) {
  return `<div class="empty">${escapeHtml(message)}</div>`;
}

function money(value) {
  return moneyFmt.format(Number(value) || 0);
}

function number(value) {
  return numberFmt.format(Number(value) || 0);
}

function compactNumber(value) {
  const n = Number(value) || 0;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(Math.round(n));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
