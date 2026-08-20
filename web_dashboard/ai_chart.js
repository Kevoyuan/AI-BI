/**
 * Boulangerie Ledger — AI chart renderer on ECharts (vendored locally).
 *
 * The AI assistant emits a fenced block in its answer; the frontend parses it
 * and mounts an interactive ECharts instance (tooltip / dataZoom / legend).
 *
 * Two accepted block types:
 *   1. ```chart  — simple spec (recommended, easy for the model):
 *        { "type":"line|bar|hbar|pie", "title":"...",
 *          "labels":["06-01",...],
 *          "series":[{"name":"实收金额","values":[...],"color":"#98651a"}],
 *          "unit":"元" }
 *   2. ```echarts — raw ECharts option JSON (advanced / other chart needs).
 *        { "xAxis":{...}, "yAxis":{...}, "series":[...] }   (data only, no functions)
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.AIChart = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SUPPORTED = ["line", "bar", "hbar", "pie", "gauge", "scatter"];
  const RAW_OPTION_MAX = 20000; // chars for ```echarts blocks
  const PALETTE = [
    "#98651a", "#c47f3a", "#7c5113", "#b8a07e",
    "#a3b18a", "#d8cfc2", "#e0b1a0", "#8d6e63",
  ];

  const _instances = new Set();

  const escapeHtml = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  function fmtVal(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "";
    const abs = Math.abs(n);
    if (abs >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    if (abs >= 1000) return Math.round(n).toLocaleString("zh-CN");
    return String(Math.round(n));
  }

  function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  function validateSpec(spec) {
    if (!spec || typeof spec !== "object") return "spec 必须是对象";
    if (!SUPPORTED.includes(spec.type)) return `type 必须是 ${SUPPORTED.join("/")}`;
    if (spec.type === "gauge") return null; // gauge can have custom fields
    if (!Array.isArray(spec.labels) || spec.labels.length === 0) return "labels 不能为空";
    if (!Array.isArray(spec.series) || spec.series.length === 0) return "series 不能为空";
    if (spec.labels.length > 80) return "labels 过多（>80）";
    if (spec.series.length > 4) return "series 过多（>4）";
    for (const s of spec.series) {
      if (!Array.isArray(s.values)) return "series.values 必须是数组";
      if (s.values.length !== spec.labels.length) return "series.values 长度与 labels 不一致";
    }
    return null;
  }

  function parseChartBlock(text) {
    let spec;
    try {
      spec = JSON.parse(text);
    } catch (_) {
      return null;
    }
    return validateSpec(spec) ? null : spec;
  }

  function parseRawOption(text) {
    let option;
    try {
      option = JSON.parse(text);
    } catch (_) {
      return null;
    }
    if (!option || typeof option !== "object" || Array.isArray(option)) return null;
    if (text.length > RAW_OPTION_MAX) return null;
    return option;
  }

  // ---------- spec → ECharts option ----------
  function seriesColor(s, idx) {
    return typeof s?.color === "string" && /^#[0-9a-fA-F]{6}$/.test(s.color)
      ? s.color
      : PALETTE[idx % PALETTE.length];
  }

  const axisTooltip = { trigger: "axis", confine: true };
  const itemTooltip = {
    trigger: "item",
    confine: true,
    formatter: "{b}<br/>{c} ({d}%)",
  };

  function specToOption(spec) {
    const labels = Array.isArray(spec.labels) ? spec.labels.slice() : [];
    const n = labels.length;
    const seriesList = Array.isArray(spec.series) ? spec.series : [];
    const values = seriesList.map((s) => Array.isArray(s.values) ? s.values.map(num) : []);
    const colors = seriesList.map((s, i) => seriesColor(s, i));
    const title = spec.title ? { text: spec.title, left: 8, textStyle: { fontSize: 13, fontWeight: 600, color: "#2d2924" } } : undefined;
    const legend = { top: 4, right: 16, textStyle: { fontSize: 11, color: "#756d63" } };

    if (spec.type === "gauge") {
      const val = num(spec.value != null ? spec.value : (values[0]?.[0] || 0));
      const maxVal = num(spec.max || 100);
      const titleText = spec.title || seriesList[0]?.name || "指标达成率";
      const unit = spec.unit || "%";
      return {
        title,
        series: [
          {
            type: "gauge",
            min: 0,
            max: maxVal,
            radius: "82%",
            center: ["50%", "58%"],
            progress: {
              show: true,
              width: 12,
              itemStyle: {
                color: (typeof window !== "undefined" && window.echarts?.graphic?.LinearGradient
                  ? new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
                      { offset: 0, color: "#c89b3c" },
                      { offset: 1, color: "#7c5113" },
                    ])
                  : "#98651a"),
              },
            },
            axisLine: { lineStyle: { width: 12, color: [[1, "#e8e1d7"]] } },
            axisTick: { show: false },
            splitLine: { length: 8, lineStyle: { width: 1, color: "#d8cfc2" } },
            axisLabel: { distance: 16, color: "#756d63", fontSize: 10 },
            pointer: { length: "60%", width: 4, itemStyle: { color: "#7c5113" } },
            detail: {
              valueAnimation: true,
              formatter: `{value}${unit}`,
              color: "#2d2924",
              fontSize: 20,
              fontWeight: 600,
              offsetCenter: [0, "68%"],
            },
            title: { offsetCenter: [0, "90%"], fontSize: 12, color: "#756d63" },
            data: [{ value: val, name: titleText }],
          },
        ],
      };
    }

    if (spec.type === "pie") {
      const data = labels.map((lb, i) => ({
        name: lb,
        value: values[0]?.[i] || 0,
        itemStyle: { color: PALETTE[i % PALETTE.length] },
      }));
      return {
        color: PALETTE,
        title,
        tooltip: itemTooltip,
        legend: { ...legend, orient: "vertical", right: 10, top: 24, textStyle: { fontSize: 11 } },
        series: [
          {
            name: seriesList[0]?.name || "占比",
            type: "pie",
            radius: ["42%", "68%"],
            center: ["36%", "56%"],
            itemStyle: { borderRadius: 4, borderColor: "#fffdf9", borderWidth: 2 },
            label: { formatter: "{d}%" },
            data,
          },
        ],
      };
    }

    if (spec.type === "scatter") {
      const scatterSeries = seriesList.map((s, i) => ({
        name: s.name || "数据点",
        type: "scatter",
        symbolSize: s.size || 8,
        data: s.data || (s.values || []).map((v, idx) => [num(labels[idx] || idx), num(v)]),
        itemStyle: { color: seriesColor(s, i) },
      }));
      return {
        color: colors,
        title,
        tooltip: { trigger: "item", confine: true },
        grid: { left: 48, right: 20, top: 40, bottom: 30 },
        xAxis: { type: "value", splitLine: { lineStyle: { type: "dashed", color: "#e8e1d7" } } },
        yAxis: { type: "value", splitLine: { lineStyle: { type: "dashed", color: "#e8e1d7" } } },
        series: scatterSeries,
      };
    }

    const isHbar = spec.type === "hbar";
    const xAxis = isHbar
      ? { type: "value", axisLabel: { formatter: fmtVal } }
      : {
          type: "category",
          data: labels,
          axisLabel: { interval: n > 12 ? Math.ceil(n / 12) : 0 },
        };
    const yAxis = isHbar
      ? { type: "category", data: labels.slice().reverse(), axisLabel: { interval: 0, width: 80, overflow: "truncate" } }
      : { type: "value", axisLabel: { formatter: fmtVal } };

    const series = seriesList.map((s, i) => {
      const data = isHbar ? (s.values || []).map(num).slice().reverse() : (s.values || []).map(num);
      return {
        name: s.name || "系列" + (i + 1),
        type: spec.type === "line" ? "line" : "bar",
        data,
        smooth: spec.type === "line",
        symbol: spec.type === "line" ? "circle" : "none",
        symbolSize: 6,
        itemStyle: { color: colors[i], borderRadius: spec.type === "bar" ? [3, 3, 0, 0] : 0 },
        lineStyle: spec.type === "line" ? { width: 2.5, color: colors[i] } : undefined,
        barMaxWidth: 28,
      };
    });

    const option = {
      color: colors,
      title,
      tooltip: axisTooltip,
      legend,
      grid: { left: 56, right: 20, top: 40, bottom: isHbar ? 24 : 40 },
      xAxis,
      yAxis,
      series,
    };
    if (n > 14 && !isHbar) {
      option.dataZoom = [
        { type: "inside", start: 0, end: 100 },
        { type: "slider", height: 16, bottom: 8 },
      ];
    }
    return option;
  }

  // ---------- Specialized Artifact Renderers (DOM) ----------
  function renderMetricsArtifact(dom, rawText) {
    let items = [];
    try {
      const parsed = JSON.parse(rawText);
      items = Array.isArray(parsed) ? parsed : (parsed.items || [parsed]);
    } catch (_) {
      fallback(dom, "指标卡片格式解析失败");
      return;
    }
    dom.className = "ai-artifact-metrics-grid";
    dom.innerHTML = items.map((m) => {
      const isUp = m.trend === "up" || String(m.change || "").startsWith("+");
      const isDown = m.trend === "down" || String(m.change || "").startsWith("-");
      const badgeCls = isUp ? "pos" : (isDown ? "neg" : "");
      return `
        <div class="ai-metric-card">
          <div class="ai-metric-label">${escapeHtml(m.label || "指标")}</div>
          <div class="ai-metric-value">${escapeHtml(m.value || "—")}</div>
          ${m.change ? `<span class="ai-metric-badge ${badgeCls}">${escapeHtml(m.change)}</span>` : ""}
          ${m.note ? `<div class="ai-metric-note">${escapeHtml(m.note)}</div>` : ""}
        </div>
      `;
    }).join("");
  }

  function renderChecklistArtifact(dom, rawText) {
    let items = [];
    try {
      const parsed = JSON.parse(rawText);
      items = Array.isArray(parsed) ? parsed : (parsed.tasks || parsed.items || []);
    } catch (_) {
      fallback(dom, "行动清单格式解析失败");
      return;
    }
    dom.className = "ai-artifact-checklist";
    dom.innerHTML = `
      <div class="ai-checklist-head">
        <strong>📋 经营行动建议清单</strong>
        <small>共 ${items.length} 项</small>
      </div>
      <div class="ai-checklist-body">
        ${items.map((item, idx) => {
          const text = typeof item === "string" ? item : (item.task || item.title || "");
          const done = typeof item === "object" && item.done;
          const priority = typeof item === "object" ? (item.priority || "medium") : "medium";
          const prioLabel = priority === "high" ? "高优" : (priority === "low" ? "可选" : "推荐");
          const prioCls = priority === "high" ? "prio-high" : (priority === "low" ? "prio-low" : "prio-med");
          return `
            <label class="ai-checklist-item ${done ? "is-done" : ""}">
              <input type="checkbox" ${done ? "checked" : ""} data-idx="${idx}" />
              <span class="ai-checklist-box"></span>
              <span class="ai-checklist-text">${escapeHtml(text)}</span>
              <span class="ai-checklist-prio ${prioCls}">${prioLabel}</span>
              ${item.impact ? `<span class="ai-checklist-impact">${escapeHtml(item.impact)}</span>` : ""}
            </label>
          `;
        }).join("")}
      </div>
    `;

    // Bind check toggle
    dom.querySelectorAll('input[type="checkbox"]').forEach((chk) => {
      chk.addEventListener("change", (e) => {
        const row = e.target.closest(".ai-checklist-item");
        if (row) row.classList.toggle("is-done", e.target.checked);
      });
    });
  }

  function renderCompareArtifact(dom, rawText) {
    let obj = {};
    try {
      obj = JSON.parse(rawText);
    } catch (_) {
      fallback(dom, "对比卡片格式解析失败");
      return;
    }
    const left = obj.left || { title: "现状", items: [] };
    const right = obj.right || { title: "优化后", items: [] };
    dom.className = "ai-artifact-compare";
    dom.innerHTML = `
      ${obj.title ? `<div class="ai-compare-title">⚖️ ${escapeHtml(obj.title)}</div>` : ""}
      <div class="ai-compare-grid">
        <div class="ai-compare-col col-left">
          <div class="ai-col-head">${escapeHtml(left.title || "优化前")}</div>
          <ul>
            ${(left.items || []).map((it) => `<li>${escapeHtml(it)}</li>`).join("")}
          </ul>
        </div>
        <div class="ai-compare-col col-right">
          <div class="ai-col-head">${escapeHtml(right.title || "优化后建议")}</div>
          <ul>
            ${(right.items || []).map((it) => `<li>${escapeHtml(it)}</li>`).join("")}
          </ul>
        </div>
      </div>
    `;
  }

  function renderCalloutArtifact(dom, rawText) {
    let obj = {};
    try {
      obj = JSON.parse(rawText);
    } catch (_) {
      fallback(dom, "提示框格式解析失败");
      return;
    }
    const type = obj.type || "note";
    const icons = { note: "ℹ️", tip: "💡", important: "⚡", warning: "⚠️", caution: "🚨" };
    dom.className = `ai-artifact-callout callout-${type}`;
    dom.innerHTML = `
      <div class="ai-callout-icon">${icons[type] || "💡"}</div>
      <div class="ai-callout-content">
        ${obj.title ? `<strong>${escapeHtml(obj.title)}</strong>` : ""}
        <p>${escapeHtml(obj.content || obj.message || "")}</p>
      </div>
    `;
  }

  // ---------- mounting ----------
  function echarts() {
    const w = typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : null);
    return w && w.echarts && w.echarts.init ? w.echarts : null;
  }

  function disposeAll() {
    _instances.forEach((inst) => {
      try {
        inst.dispose();
      } catch (_) {
        /* noop */
      }
    });
    _instances.clear();
  }

  function resizeAll() {
    _instances.forEach((inst) => {
      try {
        inst.resize();
      } catch (_) {}
    });
  }

  function fallback(dom, message) {
    dom.classList.add("ai-chart-error");
    dom.textContent = message || "渲染失败";
  }

  function mount(dom, blockType, text) {
    if (blockType === "metrics" || blockType === "kpi") {
      renderMetricsArtifact(dom, text);
      return;
    }
    if (blockType === "checklist" || blockType === "action") {
      renderChecklistArtifact(dom, text);
      return;
    }
    if (blockType === "compare" || blockType === "diff") {
      renderCompareArtifact(dom, text);
      return;
    }
    if (blockType === "callout" || blockType === "alert") {
      renderCalloutArtifact(dom, text);
      return;
    }

    const ec = echarts();
    if (!ec) {
      fallback(dom, "ECharts 未加载");
      return;
    }
    let option = null;
    let err = null;
    if (blockType === "echarts") {
      option = parseRawOption(text);
      err = option ? null : "ECharts 配置格式有误";
    } else {
      const spec = parseChartBlock(text);
      err = spec ? null : "图表数据格式有误";
      if (spec) option = specToOption(spec);
    }
    if (!option) {
      fallback(dom, err || "无数据");
      return;
    }
    try {
      const inst = ec.init(dom);
      inst.setOption(option, true);
      _instances.add(inst);
      const onResize = () => inst.resize();
      window.addEventListener("resize", onResize);
      inst._aiResize = onResize;
    } catch (_) {
      fallback(dom, "图表渲染失败");
    }
  }

  return {
    renderChartSVG: null,
    specToOption,
    parseChartBlock,
    parseRawOption,
    validateSpec,
    renderMetricsArtifact,
    renderChecklistArtifact,
    renderCompareArtifact,
    renderCalloutArtifact,
    mount,
    disposeAll,
    resizeAll,
    fmtVal,
    SUPPORTED,
    escapeHtml,
  };
});
