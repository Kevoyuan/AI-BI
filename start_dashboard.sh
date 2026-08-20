#!/bin/bash
# 启动面包店经营看板服务（脱离终端常驻，适合在 WorkBuddy 之外或会话空闲后重启）
set -e

# 切换到脚本所在目录，保证相对路径（database/、.venv/、.env）正确
cd "$(dirname "$0")"

# 若已有实例在跑，先停掉，避免端口冲突。
# 用 [w]eb_dashboard 技巧避免 pkill 匹配到脚本自身/包装 shell 的命令行。
pkill -f "[w]eb_dashboard_server.py" 2>/dev/null || true
sleep 1

# nohup + & + disown：忽略挂断信号、脱离当前 shell，会话结束后继续存活
nohup .venv/bin/python web_dashboard_server.py --host 127.0.0.1 --port 8600 \
  > /tmp/dash.log 2>&1 < /dev/null &
disown

echo "看板已启动：http://127.0.0.1:8600  (pid $!)"
echo "日志：tail -f /tmp/dash.log"
