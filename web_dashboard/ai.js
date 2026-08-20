/**
 * Boulangerie Ledger — AI Assistant drawer.
 * Reads the live dashboard payload from window.DashboardState, streams
 * answers from /api/ai/chat (SSE) and renders a safe, minimal markdown.
 */

const AI = (() => {
  const win = typeof window !== "undefined" ? window : globalThis;
  const doc = typeof document !== "undefined" ? document : null;
  const AIChart = win.AIChart || null;
  const els = {
    // Dedicated page workbench elements (Primary)
    pageMessages: doc ? doc.getElementById("ai-page-messages") : null,
    pageForm: doc ? doc.getElementById("ai-page-form") : null,
    pageInput: doc ? doc.getElementById("ai-page-input") : null,
    pageSend: doc ? doc.getElementById("ai-page-send") : null,
    pageScope: doc ? doc.getElementById("ai-page-scope") : null,
    pageSuggestions: doc ? doc.getElementById("ai-page-suggestions") : null,
    welcomeCard: doc ? doc.getElementById("ai-welcome-card") : null,
    clearBtn: doc ? doc.getElementById("ai-clear-btn") : null,
    // Header & Floating trigger buttons
    openBtn: doc ? doc.getElementById("open-ai") : null,
    fabBtn: doc ? doc.getElementById("ai-fab") : null,
    // Drawer elements (Secondary fallback)
    drawer: doc ? doc.getElementById("ai-drawer") : null,
    backdrop: doc ? doc.getElementById("ai-backdrop") : null,
    dragHandle: doc ? doc.querySelector(".ai-drag-handle") : null,
    closeBtn: doc ? doc.getElementById("ai-close") : null,
    drawerMessages: doc ? doc.getElementById("ai-messages") : null,
    drawerForm: doc ? doc.getElementById("ai-form") : null,
    drawerInput: doc ? doc.getElementById("ai-input") : null,
    drawerSend: doc ? doc.getElementById("ai-send") : null,
    drawerSuggestions: doc ? doc.getElementById("ai-suggestions") : null,
    drawerScope: doc ? doc.getElementById("ai-scope") : null,
  };

  const history = []; // [{ role: "user" | "assistant", content: "..." }]
  let busy = false;

  // ----- helpers -----
  const escapeHtml = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));

  const inline = (t) => {
    let res = t
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+?)`/g, "<code>$1</code>")
      .replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener">$1</a>'
      );
    // Badges like [A类商品], [滞销], [高毛利]
    res = res.replace(/\[(A类(?:商品)?|B类(?:商品)?|C类(?:商品)?|热销|爆款|滞销|高毛利|高报损|重点关注|建议下架|推荐)\]/g, (m, tag) => {
      const cls = tag.includes("A类") || tag.includes("爆款") || tag.includes("热销") || tag.includes("高毛利")
        ? "tag-pos"
        : (tag.includes("滞销") || tag.includes("高报损") || tag.includes("下架") ? "tag-neg" : "tag-neutral");
      return `<span class="ai-badge ${cls}">${tag}</span>`;
    });
    return res;
  };

  const ARTIFACT_TYPES = new Set([
    "chart", "echarts", "metrics", "kpi", "checklist", "action", "compare", "diff", "callout", "alert"
  ]);

  function renderMarkdown(src, withCharts) {
    const lines = String(src || "").split("\n");
    let html = "";
    let inList = false;
    let listType = "";
    let inCallout = false;
    let calloutType = "note";
    let calloutBuf = [];
    let fenceType = null;
    let fenceBuf = [];
    let chartIdx = 0;
    const chartPayloads = [];
    let inTable = false;
    let tableRows = [];

    const closeCallout = () => {
      if (!inCallout) return;
      const icons = { note: "ℹ️", tip: "💡", important: "⚡", warning: "⚠️", caution: "🚨" };
      const titles = { note: "提示", tip: "建议", important: "重要", warning: "预警", caution: "注意" };
      const content = calloutBuf.map((l) => `<p>${inline(l)}</p>`).join("");
      html += `
        <div class="ai-callout callout-${calloutType}">
          <div class="ai-callout-head">
            <span class="ai-callout-icon">${icons[calloutType] || "💡"}</span>
            <strong>${titles[calloutType] || "提示"}</strong>
          </div>
          <div class="ai-callout-body">${content}</div>
        </div>
      `;
      inCallout = false;
      calloutBuf = [];
    };

    const closeTable = () => {
      if (!inTable) return;
      if (tableRows.length >= 2) {
        const isDivider = (rowStr) => /^\|?\s*:?-+:?\s*(\|?\s*:?-+:?\s*)*\|?$/.test(rowStr.trim());
        let headerRow = null;
        let dataRows = [];

        if (isDivider(tableRows[1])) {
          headerRow = tableRows[0];
          dataRows = tableRows.slice(2);
        } else {
          dataRows = tableRows;
        }

        const parseCells = (rowStr) => {
          let trimmed = rowStr.trim();
          if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
          if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
          return trimmed.split("|").map((c) => c.trim());
        };

        let tableHtml = '<div class="ai-table-wrap"><table>';
        if (headerRow) {
          const headers = parseCells(headerRow);
          tableHtml += "<thead><tr>";
          headers.forEach((h) => {
            tableHtml += `<th>${inline(escapeHtml(h))}</th>`;
          });
          tableHtml += "</tr></thead>";
        }
        if (dataRows.length) {
          tableHtml += "<tbody>";
          dataRows.forEach((r) => {
            if (!r.trim()) return;
            const cells = parseCells(r);
            tableHtml += "<tr>";
            cells.forEach((c) => {
              tableHtml += `<td>${inline(escapeHtml(c))}</td>`;
            });
            tableHtml += "</tr>";
          });
          tableHtml += "</tbody>";
        }
        tableHtml += "</table></div>";
        html += tableHtml;
      } else {
        tableRows.forEach((r) => {
          html += `<p>${inline(escapeHtml(r))}</p>`;
        });
      }
      inTable = false;
      tableRows = [];
    };

    const closeList = () => {
      if (inList) {
        html += listType === "ol" ? "</ol>" : "</ul>";
        inList = false;
      }
    };

    const flushFence = () => {
      const body = fenceBuf.join("\n");
      const lang = fenceType;
      const spec = AIChart ? AIChart.parseChartBlock(body) : null;
      const isKnownArtifact = ARTIFACT_TYPES.has(lang);
      const isChart = AIChart && (isKnownArtifact || spec !== null);

      if (isChart) {
        const type = isKnownArtifact ? lang : (spec ? spec.type : "chart");
        if (withCharts) {
          chartPayloads.push({ type, text: body });
          html += `<div class="ai-chart" data-ai-chart="${chartIdx++}"></div>`;
        } else {
          html += '<div class="ai-chart ai-chart-pending">正在渲染组件…</div>';
        }
      } else {
        html += `
          <div class="ai-code-block">
            <button class="ai-copy-btn" type="button" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText);this.textContent='已复制 ✓';setTimeout(()=>this.textContent='复制',2000)">复制</button>
            <pre><code>${escapeHtml(body)}</code></pre>
          </div>
        `;
      }
      fenceType = null;
      fenceBuf = [];
    };

    for (const raw of lines) {
      const trimmed = raw.replace(/\s+$/, "");
      if (/^```/.test(trimmed)) {
        if (fenceType) {
          flushFence();
          closeList();
          closeTable();
          closeCallout();
          continue;
        }
        closeList();
        closeTable();
        closeCallout();
        const lang = trimmed.replace(/^```/, "").trim().toLowerCase();
        fenceType = ARTIFACT_TYPES.has(lang) ? lang : (lang || "code");
        fenceBuf = [];
        continue;
      }
      if (fenceType) {
        fenceBuf.push(trimmed);
        continue;
      }

      // Check for GitHub Alerts / Callouts e.g. > [!NOTE], > [!TIP], > [!WARNING]
      const alertMatch = trimmed.match(/^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/i);
      if (alertMatch) {
        closeList();
        closeTable();
        closeCallout();
        inCallout = true;
        calloutType = alertMatch[1].toLowerCase();
        calloutBuf = [];
        continue;
      }
      if (inCallout) {
        if (trimmed.startsWith(">")) {
          calloutBuf.push(escapeHtml(trimmed.replace(/^>\s?/, "")));
          continue;
        } else if (trimmed === "") {
          closeCallout();
          continue;
        } else {
          closeCallout();
        }
      }

      // Check for Markdown table line: e.g. | col | col | or |---|---|
      const isTableLine = trimmed.startsWith("|") && (trimmed.endsWith("|") || trimmed.includes("|"));
      if (isTableLine) {
        closeList();
        closeCallout();
        if (!inTable) {
          inTable = true;
          tableRows = [];
        }
        tableRows.push(trimmed);
        continue;
      } else if (inTable) {
        closeTable();
      }

      // Check for Interactive Checklist: - [ ] or - [x]
      const checkMatch = trimmed.match(/^[-*]\s+\[([ xX])\]\s+(.*)$/);
      if (checkMatch) {
        closeTable();
        closeCallout();
        if (!inList || listType !== "chk") {
          closeList();
          html += '<ul class="ai-task-list">';
          inList = true;
          listType = "chk";
        }
        const isChecked = checkMatch[1].toLowerCase() === "x";
        const taskContent = inline(escapeHtml(checkMatch[2]));
        html += `
          <li class="ai-task-item ${isChecked ? "is-done" : ""}">
            <label>
              <input type="checkbox" ${isChecked ? "checked" : ""} onchange="this.closest('.ai-task-item').classList.toggle('is-done', this.checked)" />
              <span class="ai-task-box"></span>
              <span class="ai-task-text">${taskContent}</span>
            </label>
          </li>
        `;
        continue;
      }

      const line = escapeHtml(trimmed);
      if (/^\s*###\s+/.test(line)) {
        closeList();
        html += `<h4>${inline(line.replace(/^\s*###\s+/, ""))}</h4>`;
      } else if (/^\s*##\s+/.test(line)) {
        closeList();
        html += `<h3>${inline(line.replace(/^\s*##\s+/, ""))}</h3>`;
      } else if (/^\s*[-*]\s+/.test(line)) {
        if (!inList || listType !== "ul") {
          closeList();
          html += "<ul>";
          inList = true;
          listType = "ul";
        }
        html += `<li>${inline(line.replace(/^\s*[-*]\s+/, ""))}</li>`;
      } else if (/^\s*\d+\.\s+/.test(line)) {
        if (!inList || listType !== "ol") {
          closeList();
          html += "<ol>";
          inList = true;
          listType = "ol";
        }
        html += `<li>${inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>`;
      } else if (line.trim() === "") {
        closeList();
      } else {
        closeList();
        html += `<p>${inline(line)}</p>`;
      }
    }
    if (fenceType) flushFence();
    closeList();
    closeTable();
    closeCallout();
    return { html, chartPayloads };
  }

  function mountCharts(bubble, payloads) {
    if (!AIChart) return;
    bubble.querySelectorAll("[data-ai-chart]").forEach((div) => {
      const payload = payloads[Number(div.getAttribute("data-ai-chart"))];
      if (payload) AIChart.mount(div, payload.type, payload.text);
    });
  }

  function renderChat(bubble, text, withCharts) {
    const { html, chartPayloads } = renderMarkdown(text, withCharts);
    bubble.innerHTML = html;
    if (withCharts) mountCharts(bubble, chartPayloads);
    scrollDown();
  }

  // ----- DOM manipulation -----
  function scrollDown() {
    if (els.pageMessages) {
      els.pageMessages.scrollTop = els.pageMessages.scrollHeight;
    }
    if (els.drawerMessages) {
      els.drawerMessages.scrollTop = els.drawerMessages.scrollHeight;
    }
  }

  function appendMessage(role, text) {
    if (els.welcomeCard) {
      els.welcomeCard.style.display = "none";
    }

    const wrap = doc ? doc.createElement("div") : null;
    if (!wrap) return { innerHTML: "" };
    wrap.className = `ai-msg ai-msg-${role}`;

    const avatar = doc.createElement("div");
    avatar.className = "ai-avatar";
    avatar.innerHTML = role === "user" ? "👤" : "✦";
    wrap.appendChild(avatar);

    const bubble = doc.createElement("div");
    bubble.className = "ai-bubble";
    bubble.innerHTML = text
      ? renderMarkdown(text, true).html
      : '<span class="ai-cursor"></span>';
    wrap.appendChild(bubble);

    const container = els.pageMessages || els.drawerMessages;
    if (container) {
      container.appendChild(wrap);
    }
    scrollDown();
    return bubble;
  }

  function setScope() {
    const p = win.DashboardState && win.DashboardState.payload;
    const range = p && p.meta && p.meta.range;
    const text = range
      ? `基于「${range} · ${p.meta.source || "银豹后台接口"}」数据回答`
      : "先加载经营数据以获得更准的回答";
    if (els.pageScope) els.pageScope.textContent = text;
    if (els.drawerScope) els.drawerScope.textContent = text;
  }

  function setBusy(v) {
    busy = v;
    if (els.pageSend) els.pageSend.disabled = v;
    if (els.drawerSend) els.drawerSend.disabled = v;
  }

  // ----- Clear Conversation -----
  function clearChat() {
    history.length = 0;
    if (els.pageMessages) {
      els.pageMessages.innerHTML = "";
      if (els.welcomeCard) {
        els.welcomeCard.style.display = "";
        els.pageMessages.appendChild(els.welcomeCard);
      }
    }
    if (els.drawerMessages) {
      els.drawerMessages.innerHTML = "";
    }
    if (els.pageSuggestions) els.pageSuggestions.style.display = "";
    if (els.drawerSuggestions) els.drawerSuggestions.style.display = "";
    if (AIChart) AIChart.disposeAll();
  }

  // ----- SSE streaming request -----
  async function ask(question) {
    question = (question || "").trim();
    if (!question || busy) return;

    appendMessage("user", question);
    history.push({ role: "user", content: question });

    const payload = (win.DashboardState && win.DashboardState.payload) || null;
    setScope();
    if (els.pageSuggestions) els.pageSuggestions.style.display = "none";
    if (els.drawerSuggestions) els.drawerSuggestions.style.display = "none";

    const bubble = appendMessage("assistant", "");
    setBusy(true);

    const body = JSON.stringify({
      question,
      range: (payload && payload.meta && payload.meta.range) || "",
      history: history.slice(0, -1),
    });

    try {
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });

      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ error: "服务不可用" }));
        bubble.innerHTML = renderMarkdown("⚠️ " + (err.error || "请求失败"), true).html;
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let full = "";
      let toolActive = false;
      let isDone = false;
      while (!isDone) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split("\n\n");
        buf = events.pop();
        for (const ev of events) {
          const line = ev.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const data = line.slice(5).trim();
          if (data === "[DONE]") {
            isDone = true;
            break;
          }
          try {
            const obj = JSON.parse(data);
            if (obj.error) {
              bubble.innerHTML = renderMarkdown("⚠️ " + obj.error, true).html;
              isDone = true;
              break;
            }
            if (obj.status) {
              toolActive = true;
              bubble.innerHTML =
                '<div class="ai-tool">' +
                escapeHtml(obj.label || "正在查询数据…") +
                "</div>";
              scrollDown();
              continue;
            }
            if (obj.token) {
              if (toolActive) {
                toolActive = false;
                bubble.innerHTML = "";
              }
              full += obj.token;
              renderChat(bubble, full, false);
            }
          } catch (_) {
            /* ignore partial frames */
          }
        }
      }
      try {
        await reader.cancel();
      } catch (_) {}

      if (full) renderChat(bubble, full, true);
      history.push({ role: "assistant", content: full });
    } catch (e) {
      bubble.innerHTML = renderMarkdown("⚠️ 网络或解析错误：" + e.message, true).html;
    } finally {
      setBusy(false);
      scrollDown();
      const input = els.pageInput || els.drawerInput;
      if (input) input.focus();
    }
  }

  // ----- Navigation & Controls -----
  function navigateToAIPage() {
    if (typeof win.switchTab === "function") {
      win.switchTab("ai");
    }
    setScope();
    const input = els.pageInput || els.drawerInput;
    if (input) {
      setTimeout(() => {
        input.focus();
        scrollDown();
      }, 120);
    }
    if (AIChart && typeof AIChart.resizeAll === "function") {
      setTimeout(AIChart.resizeAll, 300);
    }
  }

  function autoGrow(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  }

  // ----- Wiring -----
  if (els.openBtn) els.openBtn.addEventListener("click", navigateToAIPage);
  if (els.fabBtn) els.fabBtn.addEventListener("click", navigateToAIPage);
  if (els.clearBtn) els.clearBtn.addEventListener("click", clearChat);

  // Page input
  if (els.pageInput) {
    els.pageInput.addEventListener("input", () => autoGrow(els.pageInput));
    els.pageInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const q = els.pageInput.value;
        els.pageInput.value = "";
        autoGrow(els.pageInput);
        els.pageInput.focus();
        ask(q);
      }
    });
  }

  if (els.pageForm) {
    els.pageForm.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!els.pageInput) return;
      const q = els.pageInput.value;
      els.pageInput.value = "";
      autoGrow(els.pageInput);
      els.pageInput.focus();
      ask(q);
    });
  }

  // Prompt Matrix click handlers
  if (doc) {
    doc.querySelectorAll(".ai-prompt-btn, .ai-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = btn.textContent.trim();
        if (q) ask(q);
      });
    });
  }

  return { ask, open: navigateToAIPage, clear: clearChat, renderMarkdown };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = AI;
}
