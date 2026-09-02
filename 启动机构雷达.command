#!/bin/zsh
# 启动机构雷达（若已在运行则直接打开浏览器）
cd "$(dirname "$0")"
PORT=8900
if lsof -ti :$PORT >/dev/null 2>&1; then
  echo "机构雷达已在运行 -> http://127.0.0.1:$PORT"
else
  nohup .venv/bin/python app.py > server.log 2>&1 &
  echo "机构雷达启动中 -> http://127.0.0.1:$PORT （首次全量抓取约 2 分钟）"
fi
sleep 1
open "http://127.0.0.1:$PORT" 2>/dev/null || true
