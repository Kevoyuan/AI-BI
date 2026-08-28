/**
 * Boulangerie Ledger — AI Assistant drawer.
 * Reads the live dashboard payload from window.DashboardState, streams
 * answers from /api/ai/chat (SSE) and renders a safe, minimal markdown.
 */

const AI = (() => {
  const win = typeof window !== "undefined" ? window : globalThis;
  const doc = typeof document !== "undefined" ? document : null;
  const AIChart = win.AIChart || null;
  const t = (value) => (win.I18n && typeof win.I18n.t === "function" ? win.I18n.t(value) : value);
  const els = {
    // Dedicated page workbench elements (Primary)
    pageMessages: doc ? doc.getElementById("ai-page-messages") : null,
    pageForm: doc ? doc.getElementById("ai-page-form") : null,
    pageInput: doc ? doc.getElementById("ai-page-input") : null,
    pageSend: doc ? doc.getElementById("ai-page-send") : null,
    pageScope: doc ? doc.getElementById("ai-page-scope") : null,
    costSummary: doc ? doc.getElementById("ai-cost-summary") : null,
    newBtn: doc ? doc.getElementById("ai-new-btn") : null,
    sessionList: doc ? doc.getElementById("ai-session-list") : null,
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

  const STORAGE_KEY = "ai-bi.sessions.v1";
  const SESSION_LIMIT = 20;
  const MESSAGE_LIMIT = 40;
  const SSE_INACTIVITY_MS = 90_000;
  let history = []; // [{ role: "user" | "assistant", content: "..." }]
  let sessions = [];
  let currentSessionId = "";
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
    let res = escapeHtml(t)
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
      const titles = {
        note: t("提示"), tip: t("建议"), important: t("重要"), warning: t("预警"), caution: t("注意"),
      };
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
          html += `<div class="ai-chart ai-chart-pending">${t("正在渲染组件…")}</div>`;
        }
      } else {
        html += `
          <div class="ai-code-block">
            <button class="ai-copy-btn" type="button" onclick="navigator.clipboard.writeText(this.nextElementSibling.innerText);this.textContent='${t("已复制")} ✓';setTimeout(()=>this.textContent='${t("复制")}',2000)">${t("复制")}</button>
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

  // ----- Browser-owned session store -----
  function storage() {
    try {
      return win.localStorage || null;
    } catch (_) {
      return null;
    }
  }

  function makeSession() {
    const stamp = Date.now();
    return {
      id: `session-${stamp}-${Math.random().toString(36).slice(2, 8)}`,
      title: "新对话",
      messages: [],
      usage: { inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, totalTokens: 0, costUsd: 0, cacheSavingsUsd: 0 },
      createdAt: stamp,
      updatedAt: stamp,
    };
  }

  function saveSessions() {
    const store = storage();
    if (!store) return;
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, SESSION_LIMIT)));
    } catch (_) {
      // Storage can be disabled or full; the current in-memory session still works.
    }
  }

  function loadSessions() {
    const store = storage();
    let saved = [];
    try {
      saved = store ? JSON.parse(store.getItem(STORAGE_KEY) || "[]") : [];
    } catch (_) {}
    if (!Array.isArray(saved)) saved = [];
    sessions = saved
      .filter((s) => s && typeof s.id === "string")
      .slice(0, SESSION_LIMIT)
      .map((s) => ({
        ...makeSession(),
        ...s,
        messages: Array.isArray(s.messages)
          ? s.messages.filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string").slice(-MESSAGE_LIMIT)
          : [],
        usage: { ...makeSession().usage, ...(s.usage || {}) },
      }));
    if (!sessions.length) sessions = [makeSession()];
    currentSessionId = sessions[0].id;
    const current = sessions[0];
    history = current.messages.slice();
    saveSessions();
  }

  function currentSession() {
    return sessions.find((s) => s.id === currentSessionId) || sessions[0];
  }

  function persistCurrent() {
    const session = currentSession();
    if (!session) return;
    session.messages = history.slice(-MESSAGE_LIMIT);
    session.updatedAt = Date.now();
    const firstQuestion = history.find((m) => m.role === "user" && m.content);
    if (firstQuestion && session.title === "新对话") {
      session.title = firstQuestion.content.replace(/\s+/g, " ").slice(0, 28) || "新对话";
    }
    sessions.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    saveSessions();
    renderSessionList();
    renderUsage();
  }

  function renderUsage() {
    const usage = currentSession()?.usage || {};
    const cost = Number(usage.costUsd || 0).toFixed(4);
    const locale = win.I18n?.language === "en" ? "en-US" : "zh-CN";
    const tokens = Number(usage.totalTokens || 0).toLocaleString(locale);
    const savings = Number(usage.cacheSavingsUsd || 0);
    const savedText = savings > 0 ? ` · ${t("缓存节省")} $${savings.toFixed(4)}` : "";
    const text = `${t("本会话成本")} $${cost} · ${tokens} ${t("tokens")}${savedText}`;
    if (els.costSummary) els.costSummary.textContent = text;
  }

  function renderSessionList() {
    if (!els.sessionList || !doc) return;
    els.sessionList.innerHTML = "";
    sessions.slice(0, SESSION_LIMIT).forEach((session) => {
      const btn = doc.createElement("button");
      btn.type = "button";
      btn.className = `ai-session-item${session.id === currentSessionId ? " active" : ""}`;
      btn.dataset.sessionId = session.id;
      btn.title = t(session.title || "新对话");
      btn.textContent = t(session.title || "新对话");
      els.sessionList.appendChild(btn);
    });
  }

  function renderHistory() {
    if (els.pageMessages) els.pageMessages.innerHTML = "";
    if (els.drawerMessages) els.drawerMessages.innerHTML = "";
    if (!history.length && els.pageMessages && els.welcomeCard) {
      els.pageMessages.appendChild(els.welcomeCard);
      els.welcomeCard.style.display = "";
    } else {
      history.forEach((message) => appendMessage(message.role, message.content));
    }
    if (els.pageSuggestions) els.pageSuggestions.style.display = history.length ? "none" : "";
    if (els.drawerSuggestions) els.drawerSuggestions.style.display = history.length ? "none" : "";
    renderUsage();
    scrollDown();
  }

  function selectSession(id) {
    if (busy || !sessions.some((s) => s.id === id)) return;
    currentSessionId = id;
    history = (currentSession()?.messages || []).slice();
    renderSessionList();
    renderHistory();
  }

  function newSession() {
    if (busy) return;
    const session = makeSession();
    sessions.unshift(session);
    sessions = sessions.slice(0, SESSION_LIMIT);
    currentSessionId = session.id;
    history = [];
    saveSessions();
    renderSessionList();
    renderHistory();
    const input = els.pageInput || els.drawerInput;
    if (input) input.focus();
  }

  function recordUsage(usage) {
    const session = currentSession();
    if (!session || !usage) return;
    const numeric = ["inputTokens", "cachedInputTokens", "outputTokens", "totalTokens", "costUsd", "cacheSavingsUsd"];
    numeric.forEach((key) => {
      const value = Number(usage[key] || 0);
      if (Number.isFinite(value)) session.usage[key] = Number(session.usage[key] || 0) + value;
    });
    session.usage.priceVersion = usage.priceVersion || session.usage.priceVersion || "env-configured";
    session.usage.model = usage.model || session.usage.model || "";
    persistCurrent();
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
    const rendered = text
      ? renderMarkdown(text, true)
      : { html: '<span class="ai-cursor"></span>', chartPayloads: [] };
    bubble.innerHTML = rendered.html;
    wrap.appendChild(bubble);

    const container = els.pageMessages || els.drawerMessages;
    if (container) {
      container.appendChild(wrap);
    }
    if (role === "assistant" && rendered.chartPayloads.length) {
      mountCharts(bubble, rendered.chartPayloads);
    }
    scrollDown();
    return bubble;
  }

  function setScope() {
    const p = win.DashboardState && win.DashboardState.payload;
    const range = p && p.meta && p.meta.range;
    const text = range
      ? `${t("基于")}「${range} · ${p.meta.source || t("银豹后台接口")}」${t("数据回答")}`
      : t("先加载经营数据以获得更准的回答");
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
    if (busy) return;
    history = [];
    const session = currentSession();
    if (session) {
      session.title = "新对话";
      session.usage = { inputTokens: 0, cachedInputTokens: 0, outputTokens: 0, totalTokens: 0, costUsd: 0, cacheSavingsUsd: 0 };
    }
    persistCurrent();
    renderHistory();
    if (AIChart) AIChart.disposeAll();
  }

  // ----- SSE streaming request -----
  function isRetryable(error) {
    return Boolean(error && (error.retryable || error.name === "TypeError" || error.name === "AbortError"));
  }

  async function consumeStream(response, bubble, controller) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let full = "";
    let usage = null;
    let toolActive = false;
    let isDone = false;
    let timedOut = false;
    let inactivityTimer = null;

    const armInactivityTimer = () => {
      if (inactivityTimer) clearTimeout(inactivityTimer);
      inactivityTimer = setTimeout(() => {
        timedOut = true;
        controller.abort();
        reader.cancel().catch(() => {});
      }, SSE_INACTIVITY_MS);
    };
    armInactivityTimer();
    try {
      while (!isDone) {
        const { value, done } = await reader.read();
        armInactivityTimer();
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
          const obj = JSON.parse(data);
          if (obj.error) {
            const error = new Error(obj.error);
            error.retryable = true;
            throw error;
          }
          if (obj.usage) {
            usage = obj.usage;
            continue;
          }
          if (obj.status) {
            toolActive = true;
            bubble.innerHTML = '<div class="ai-tool">' + escapeHtml(t(obj.label || "正在查询数据…")) + "</div>";
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
        }
      }
      if (timedOut) {
        const error = new Error("90 秒内没有收到新的回答，连接已自动停止");
        error.retryable = true;
        throw error;
      }
      return { full, usage };
    } catch (error) {
      if (timedOut || error?.name === "AbortError") {
        const timeoutError = new Error("90 秒内没有收到新的回答，连接已自动停止");
        timeoutError.retryable = true;
        throw timeoutError;
      }
      throw error;
    } finally {
      if (inactivityTimer) clearTimeout(inactivityTimer);
      try { await reader.cancel(); } catch (_) {}
    }
  }

  async function streamAttempt(question, priorHistory, bubble) {
    const payload = (win.DashboardState && win.DashboardState.payload) || null;
    const controller = new AbortController();
    const body = JSON.stringify({
      question,
      range: (payload && payload.meta && payload.meta.range) || "",
      // The browser session is the source of truth. Do not also send a
      // thread_id: a server checkpointer would append these messages again.
      history: priorHistory,
      history_mode: "client",
    });
    let response;
    try {
      response = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: controller.signal,
      });
    } catch (error) {
      throw error;
    }
    if (!response.ok || !response.body) {
      const err = await response.json().catch(() => ({ error: "服务不可用" }));
      const error = new Error(err.error || "请求失败");
      error.retryable = response.status === 408 || response.status === 429 || response.status >= 500;
      throw error;
    }
    // consumeStream owns the reader-level inactivity timer. The controller
    // is retained for browsers that abort a response while it is being read.
    return consumeStream(response, bubble, controller);
  }

  function showRetry(bubble, message, question) {
    bubble.innerHTML = renderMarkdown("⚠️ " + message, true).html;
    if (!doc) return;
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "ai-retry-btn";
    button.textContent = t("重试本次提问");
    button.addEventListener("click", () => {
      const wrap = bubble.parentElement;
      if (wrap) wrap.remove();
      ask(question, { reuseUserMessage: true });
    });
    bubble.appendChild(button);
  }

  async function ask(question, options = {}) {
    question = (question || "").trim();
    if (!question || busy) return;

    if (!options.reuseUserMessage) {
      appendMessage("user", question);
      history.push({ role: "user", content: question });
      persistCurrent();
    }

    setScope();
    if (els.pageSuggestions) els.pageSuggestions.style.display = "none";
    if (els.drawerSuggestions) els.drawerSuggestions.style.display = "none";

    const bubble = appendMessage("assistant", "");
    setBusy(true);
    bubble.innerHTML = `<div class="ai-tool">${t("正在思考，通常需要几秒…")}</div>`;

    try {
      let result = null;
      let lastError = null;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        if (attempt > 0) {
          bubble.innerHTML = `<div class="ai-tool">${t("连接稍慢，正在重试（2/2）…")}</div>`;
        }
        try {
          result = await streamAttempt(question, history.slice(0, -1), bubble);
          break;
        } catch (error) {
          lastError = error;
          if (attempt === 0 && isRetryable(error)) continue;
          break;
        }
      }
      if (!result) {
        showRetry(bubble, `网络或解析错误：${lastError?.message || "请求失败"}`, question);
        return;
      }
      if (result.full) renderChat(bubble, result.full, true);
      history.push({ role: "assistant", content: result.full || "" });
      persistCurrent();
      recordUsage(result.usage);
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
  if (els.newBtn) els.newBtn.addEventListener("click", newSession);
  if (els.clearBtn) els.clearBtn.addEventListener("click", clearChat);
  if (els.sessionList) {
    els.sessionList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-session-id]");
      if (button) selectSession(button.dataset.sessionId);
    });
  }

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

  loadSessions();
  renderSessionList();
  renderHistory();
  if (typeof win.addEventListener === "function") {
    win.addEventListener("languagechange", () => {
      setScope();
      renderUsage();
      renderSessionList();
      renderHistory();
    });
  }

  return {
    ask,
    open: navigateToAIPage,
    clear: clearChat,
    newSession,
    selectSession,
    renderMarkdown,
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = AI;
}
