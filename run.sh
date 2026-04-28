#!/bin/bash
# 启动 douyin-bot：加载 .env 后运行 bot.py
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "❌ 缺少 .env 文件"
    exit 1
fi

set -a
source .env
set +a

exec /opt/homebrew/bin/python3.11 bot.py
