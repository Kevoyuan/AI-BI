// AI chart spec → ECharts option tests (no DOM / no echarts needed).
// Run: node tests/ai_chart_render.test.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const AIChart = require("../web_dashboard/ai_chart.js");

let passed = 0;
const ok = (name) => {
  passed++;
  console.log("ok -", name);
};

// --- parseChartBlock / validateSpec ---
const lineSpec = {
  type: "line",
  title: "本周销售额",
  labels: ["周一", "周二", "周三"],
  series: [{ name: "实收金额", values: [12000, 15000, 13000] }],
};
assert.deepEqual(AIChart.parseChartBlock(JSON.stringify(lineSpec)), lineSpec);
ok("parseChartBlock round-trips a valid line spec");

assert.equal(AIChart.parseChartBlock("{bad json"), null);
assert.equal(AIChart.parseChartBlock(JSON.stringify({ type: "pie", labels: ["a"], series: [] })), null);
assert.equal(
  AIChart.parseChartBlock(JSON.stringify({ type: "funnel", labels: ["a"], series: [{ values: [1] }] })),
  null,
  "unsupported type rejected"
);
ok("invalid specs rejected (bad json / empty series / unknown type)");

// --- specToOption ---
const lineOption = AIChart.specToOption(lineSpec);
assert.equal(lineOption.series[0].type, "line");
assert.deepEqual(lineOption.xAxis.data, ["周一", "周二", "周三"]);
assert.deepEqual(lineOption.series[0].data, [12000, 15000, 13000]);
assert.equal(lineOption.tooltip.trigger, "axis");
ok("line spec maps to an ECharts option with axis tooltip");

const barSpec = { ...lineSpec, type: "bar", labels: Array.from({ length: 20 }, (_, i) => "D" + (i + 1)), series: [{ name: "x", values: Array.from({ length: 20 }, (_, i) => i * 100) }] };
const barOption = AIChart.specToOption(barSpec);
assert.equal(barOption.series[0].type, "bar");
assert.ok(Array.isArray(barOption.dataZoom), "long series gets dataZoom (interaction)");
ok("bar spec adds dataZoom for >14 points");

const pieOption = AIChart.specToOption({ type: "pie", labels: ["现烤", "西点"], series: [{ values: [60, 40] }] });
assert.equal(pieOption.series[0].type, "pie");
assert.equal(pieOption.series[0].radius[0], "42%");
assert.equal(pieOption.tooltip.trigger, "item");
ok("pie spec maps to donut series with item tooltip");

const hbarOption = AIChart.specToOption({ type: "hbar", labels: ["A", "B"], series: [{ values: [3, 8] }] });
assert.equal(hbarOption.yAxis.type, "category");
assert.deepEqual(hbarOption.yAxis.data, ["B", "A"], "hbar reverses labels for top-down reading");
ok("hbar maps labels to category yAxis (reversed)");

// --- parseRawOption (```echarts) ---
const raw = AIChart.parseRawOption('{"xAxis":{"type":"category"},"series":[{"type":"scatter","data":[[0,1]]}]}');
assert.ok(raw && raw.series[0].type === "scatter");
ok("raw echarts option parsed");

assert.equal(AIChart.parseRawOption("[1,2,3]"), null, "array is not a valid option");
assert.equal(AIChart.parseRawOption('"string"'), null);
assert.equal(AIChart.parseRawOption('{"a":' + "x".repeat(21000) + "}"), null, "oversized option rejected");
ok("raw option rejects arrays / strings / oversized payloads");

// --- fmtVal ---
assert.equal(AIChart.fmtVal(123456), "12.3万");
assert.equal(AIChart.fmtVal(1500), "1,500");
ok("fmtVal formats 万 / thousands");

// --- markdown table rendering ---
const AI = require("../web_dashboard/ai.js");
const sampleTableMarkdown = `
| 商品 | 品类 | 3个月实收 | 卖了几次 |
|---|---|---|---|
| 爆浆麻薯 | 现烤 | 8 元 | 1次 |
| 弯曲蜡烛 | 其他 | 9 元 | 3次 |
`;
const tableRes = AI.renderMarkdown(sampleTableMarkdown, false);
assert.ok(tableRes.html.includes('<div class="ai-table-wrap"><table>'));
assert.ok(tableRes.html.includes("<th>商品</th>"));
assert.ok(tableRes.html.includes("<th>3个月实收</th>"));
assert.ok(tableRes.html.includes("<td>爆浆麻薯</td>"));
assert.ok(tableRes.html.includes("<td>8 元</td>"));
ok("renderMarkdown renders structured markdown tables");

// --- gauge spec ---
const gaugeOption = AIChart.specToOption({ type: "gauge", title: "目标达成率", value: 85, max: 100, unit: "%" });
assert.equal(gaugeOption.series[0].type, "gauge");
assert.equal(gaugeOption.series[0].data[0].value, 85);
ok("gauge spec maps to gauge ECharts option");

// --- scatter spec ---
const scatterOption = AIChart.specToOption({ type: "scatter", labels: [1, 2], series: [{ values: [10, 20] }] });
assert.equal(scatterOption.series[0].type, "scatter");
ok("scatter spec maps to scatter ECharts option");

// --- specialized DOM artifacts ---
const mockDom = {
  className: "",
  innerHTML: "",
  querySelectorAll: () => [],
};
AIChart.renderMetricsArtifact(mockDom, JSON.stringify([{ label: "实收", value: "1.2万", change: "+10%", trend: "up" }]));
assert.ok(mockDom.innerHTML.includes("ai-metric-card"));
assert.ok(mockDom.innerHTML.includes("1.2万"));
assert.ok(mockDom.innerHTML.includes("pos"));
ok("renderMetricsArtifact produces metric cards with positive badge");

AIChart.renderChecklistArtifact(mockDom, JSON.stringify([{ task: "推出下午茶套餐", done: false, priority: "high" }]));
assert.ok(mockDom.className.includes("ai-artifact-checklist"));
assert.ok(mockDom.innerHTML.includes("推出下午茶套餐"));
assert.ok(mockDom.innerHTML.includes("prio-high"));
ok("renderChecklistArtifact produces actionable checklist with priority badges");

AIChart.renderCompareArtifact(mockDom, JSON.stringify({ title: "对比", left: { title: "前", items: ["a"] }, right: { title: "后", items: ["b"] } }));
assert.ok(mockDom.className.includes("ai-artifact-compare"));
assert.ok(mockDom.innerHTML.includes("col-left"));
assert.ok(mockDom.innerHTML.includes("col-right"));
ok("renderCompareArtifact produces side-by-side comparison cards");

AIChart.renderCalloutArtifact(mockDom, JSON.stringify({ type: "warning", title: "预警", content: "报损过高" }));
assert.ok(mockDom.className.includes("callout-warning"));
assert.ok(mockDom.innerHTML.includes("报损过高"));
ok("renderCalloutArtifact produces structured callout");

// --- markdown callouts & task lists ---
const calloutMd = `
> [!WARNING]
> 现烤报损偏高，需注意。
`;
const calloutRes = AI.renderMarkdown(calloutMd, false);
assert.ok(calloutRes.html.includes("callout-warning"));
assert.ok(calloutRes.html.includes("预警"));
assert.ok(calloutRes.html.includes("现烤报损偏高"));
ok("renderMarkdown renders GitHub style > [!WARNING] alerts");

const taskMd = `
- [ ] 开展盲盒打折
- [x] 下调每日备货
`;
const taskRes = AI.renderMarkdown(taskMd, false);
assert.ok(taskRes.html.includes("ai-task-list"));
assert.ok(taskRes.html.includes("开展盲盒打折"));
assert.ok(taskRes.html.includes("is-done"));
ok("renderMarkdown renders interactive task lists (- [ ] / - [x])");

// --- code block with copy button ---
const codeMd = "```python\nprint(1)\n```";
const codeRes = AI.renderMarkdown(codeMd, false);
assert.ok(codeRes.html.includes("ai-copy-btn"));
assert.ok(codeRes.html.includes("print(1)"));
ok("renderMarkdown adds copy button to code blocks");

console.log(`\nALL ${passed} AI TESTS PASSED`);
