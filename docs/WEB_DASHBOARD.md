# Web Dashboard 运行与架构

## 定位

`web_dashboard/` 是项目当前唯一的主经营 Dashboard。它由 `web_dashboard_server.py` 提供静态资源和同源 JSON API，实时业务数据来自银豹 Web 后台导出。

旧版 Streamlit 不是主入口，也不应承接新的 Dashboard 功能。需要兼容旧分析页面时，请参考 [LEGACY_STREAMLIT.md](LEGACY_STREAMLIT.md)。

## 启动

```bash
cp .env.example .env
# 可选：设置 POSPAL_USER 和 POSPAL_PASSWORD；公开演示默认使用脱敏预热缓存

python3 web_dashboard_server.py --host 127.0.0.1 --port 8600
```

访问 <http://localhost:8600>。`/` 和 `/dashboard` 都返回主页面。

服务默认监听 `0.0.0.0`。仅在本机使用时应显式传入 `--host 127.0.0.1`；需要局域网访问时才绑定到可外部访问的地址。

当前服务器没有终端用户登录或 TLS；但数据进入 Dashboard 前会经过隐私边界处理，会员、交易、支付、员工和门店标识会替换为合成占位值。公开仓库内置的预热缓存不包含真实凭据或原始个人标识。若配置真实银豹凭据用于本地开发，仍应只在受信任的本机使用，并在正式部署前增加鉴权、HTTPS、访问控制和日志审计。

## 组件职责

| 组件 | 职责 |
|---|---|
| `web_dashboard/index.html` | 页面结构、Tab、筛选器和渲染容器 |
| `web_dashboard/styles.css` | 响应式布局、视觉样式和状态样式 |
| `web_dashboard/i18n.js` | 中 / 英 UI 切换、浏览器持久化和动态文案翻译 |
| `web_dashboard/app.js` | 请求 API、维护页面状态、生成表格和 SVG 图表 |
| `web_dashboard_server.py` | 静态文件服务、查询参数解析、错误响应和 payload 缓存 |
| `modules/dashboard_api.py` | 日期范围处理、数据聚合、KPI 和业务洞察 |
| `modules/pospal_live_data.py` | 银豹登录、月度报表下载、解析和月度缓存 |

## 请求流程

```text
页面加载
  └─ GET /api/dashboard?preset=month
       ├─ 解析 preset / 月份 / 自定义日期
       ├─ 下载所需月份的银豹报表（跨月范围会下载多个月份）
       ├─ 对销售、报损、储值、充值和销售明细应用闭区间筛选
       ├─ 计算 Dashboard payload
       └─ 返回 JSON 并渲染页面
```

## API

### `GET /api/dashboard`

查询解析顺序：

1. 先解析有效的 `preset`（`today`、`yesterday`、`week`、`month`）；没有 preset 时解析 `year` 和 `month`
2. 同时提供的 `date_from` 和 `date_to` 会覆盖上述范围
3. 未提供有效范围参数时使用当前月份

支持的日期别名：

- 开始日期：`date_from`、`from`、`start_date`、`start`
- 结束日期：`date_to`、`to`、`end_date`、`end`

示例：

```text
/api/dashboard?preset=today
/api/dashboard?year=2026&month=8
/api/dashboard?date_from=2026-07-28&date_to=2026-08-03
/api/dashboard?preset=month&refresh=1
```

错误响应为 JSON，包含 `error`；服务器内部异常还包含 `type`。只提供一个日期边界会返回 HTTP 400。

### `POST /api/ai/chat`

AI 助手使用同源 SSE 返回流式事件。浏览器会话是历史记录的唯一来源，服务端会过滤消息角色、限制为最近 10 条并将单条消息截断到 6000 个字符，避免历史重复注入和异常请求体膨胀。

请求体示例：

```json
{
  "question": "这周报损率是不是偏高？",
  "range": "2026-08",
  "history_mode": "client",
  "history": [
    {"role": "user", "content": "上周销售怎么样？"},
    {"role": "assistant", "content": "上周实收约 3.2 万元。"}
  ]
}
```

事件类型包括 `token`、工具调用时的 `status`、回答结束前的 `usage` 和 `[DONE]`。`usage` 包含输入/输出 Token、缓存命中、价格版本、估算成本和缓存节省金额。LLM 超时与费率可通过 `DEEPSEEK_TIMEOUT_SECONDS`、`DEEPSEEK_MAX_RETRIES`、`DEEPSEEK_INPUT_USD_PER_MILLION`、`DEEPSEEK_CACHED_INPUT_USD_PER_MILLION`、`DEEPSEEK_OUTPUT_USD_PER_MILLION` 和 `DEEPSEEK_PRICE_VERSION` 配置。

## 缓存与刷新

系统有两层内存缓存：

| 层级 | 默认 TTL | 内容 |
|---|---:|---|
| HTTP payload | 300 秒 | 某个查询范围的完整 Dashboard JSON |
| 银豹月度报表 | 600 秒 | 解析后的月度 DataFrame 集合 |

`refresh=1` 会跳过 payload 缓存并清空月度报表缓存，然后重新从银豹下载。缓存仅存在于当前 Python 进程，重启服务会全部清空。

## 数据与财务口径

- 实时销售、报损、储值和明细来自银豹后台导出的 Excel 文件。
- 下载文件只存在于临时目录，解析完成后自动清理。
- 主 Dashboard 不把实时销售、报损、储值和明细写入月度 SQLite 数据库。
- 净利润路径会合并 `database/` 下所有月度数据库的 `financial` 行，取最后一行固定支出、第一行原料成本比和运营管理比；参数不是按查询月份选择。
- 当前实现要求至少有一个可读取且包含 `financial` 表的数据库。完全没有数据库时，`modules.database` 会调用 `st.stop()`，HTTP 请求可能中止，而不是返回零成本估算。
- 净利润是经营估算，不等同于最终会计利润。
- 自定义日期范围是包含开始日和结束日的闭区间。

## 开发验证

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_dashboard_api.py \
  tests/test_pospal_live_data.py

node tests/dashboard_render.mjs

python3 -m py_compile \
  web_dashboard_server.py \
  modules/dashboard_api.py \
  modules/pospal_live_data.py
```

前端测试使用模拟 payload 执行所有主要 renderer，确保每个目标容器都产生内容。后端测试覆盖日期筛选、跨数据集过滤、报表解析和月度缓存隔离。

## 常见问题

### 直接打开 HTML 没有样式或数据

不要通过 `file://` 打开 `web_dashboard/index.html`。页面使用 `/styles.css`、`/app.js` 和 `/api/dashboard` 根路径，必须通过 `web_dashboard_server.py` 访问。

### 页面一直加载

查看服务器终端是否完成银豹登录和报表导出。首次加载或强制刷新需要下载多个 Excel 文件，通常比命中缓存慢。

若需要切换到本地真实银豹数据，确认 `.env` 中同时设置了 `POSPAL_USER` 和 `POSPAL_PASSWORD`；公开演示不需要这些变量，直接使用仓库内的脱敏预热缓存。

### 端口被占用

指定其他端口：

```bash
python3 web_dashboard_server.py --host 127.0.0.1 --port 8601
```

### 修改前端后看不到变化

硬刷新浏览器。静态文件本身没有服务端构建步骤；HTML、CSS 和 JavaScript 保存后即可由服务器返回。
