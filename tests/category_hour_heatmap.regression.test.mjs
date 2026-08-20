import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// Regression: ISSUE-006 — narrow screens rendered the category/hour heatmap with
// an oversized label track and unused hour columns, clipping every value.
// Found by /qa on 2026-08-08
// Report: .gstack/qa-reports/qa-report-localhost-8600-2026-08-08.md
const source = readFileSync("web_dashboard/app.js", "utf8");
const start = source.indexOf("function renderCategoryByHour");
const end = source.indexOf("function renderOrderAmountDist", start);
assert.ok(start >= 0 && end > start, "renderCategoryByHour source was not found");

const sandbox = {
  els: { catHourHeat: { innerHTML: "" } },
  empty: (message) => `<div class="empty">${message}</div>`,
  escapeHtml: (value) => String(value),
  money: (value) => `¥${value}`,
};
vm.runInNewContext(`${source.slice(start, end)}\nthis.renderCategoryByHour = renderCategoryByHour;`, sandbox);

// Precondition: the API includes empty early hours plus the visible 10:00–22:00 range.
sandbox.renderCategoryByHour([
  { 收入分类: "现烤", 小时: 7, 实收金额: 0 },
  { 收入分类: "现烤", 小时: 9, 实收金额: 0 },
  { 收入分类: "现烤", 小时: 10, 实收金额: 120 },
  { 收入分类: "现烤", 小时: 12, 实收金额: 240 },
  { 收入分类: "现烤", 小时: 22, 实收金额: 60 },
]);

const html = sandbox.els.catHourHeat.innerHTML;
assert.match(html, /minmax\(48px, 54px\) repeat\(3, minmax\(0, 1fr\)\)/);
assert.match(html, /class="chh-hour-label">10<\/div>/);
assert.match(html, /class="chh-hour-label">22<\/div>/);
assert.doesNotMatch(html, /class="chh-hour-label">(?:7|9|23)<\/div>/);

console.log("✓ category/hour heatmap uses only visible hours and compact grid tracks");
