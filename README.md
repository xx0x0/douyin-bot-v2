# douyin-bot
抖音/X 视频文案提取 Telegram Bot 一个运行在本地 Mac 上的 Telegram Bot，支持抖音、X(Twitter)、YouTube、B站等平台的视频下载和文案提取，完全免费，数据不上云。 本地 AI 模型梳理总结长文案 
# 抖音/X 视频文案提取 Telegram Bot

一个运行在本地 Mac 上的 Telegram Bot，支持抖音、X(Twitter)、YouTube、B站等平台的视频下载和文案提取，完全免费，数据不上云。

---

## ✨ 功能

- 📥 **无水印视频下载** — 抖音无需登录直接下载，其他平台需配置 cookie
- 🎙️ **本地语音转文案** — 使用 Whisper，完全离线，中文识别准确
- 🤖 **AI 文案梳理** — 使用本地 Ollama + qwen2.5:7b，超过800字自动梳理
- 🔗 **链接去追踪** — 抖音短链自动解析成干净的数字 ID 链接
- 📝 **X 推文提取** — 自动提取推文原文，不转文案
- 🖼️ **图文识别** — 自动识别抖音图文笔记并提示
- 🔒 **白名单保护** — 只响应指定用户和群组

---

## 📤 输出格式

**抖音/其他平台：**
```
[视频文件]

视频标题：xxx

文案：
[Whisper 识别的完整文案]

原视频链接：https://www.douyin.com/video/xxx
```

**文案超过800字时额外输出：**
```
视频标题：xxx

梳理后的文案：
[AI 梳理内容]

原视频链接：https://...
```

**X/Twitter：**
```
[视频文件]

📝 推文内容：
[推文原文]

🔗：https://x.com/...
```

---

## 📋 系统要求

- macOS（Apple Silicon 推荐，M1/M2/M3/M4）
- Python 3.11+
- 16GB 内存以上

---

## 🚀 安装步骤

### 1. 安装基础工具

```bash
brew install node@24 yt-dlp ffmpeg python@3.11 uv ollama
echo 'export PATH="/opt/homebrew/opt/node@24/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 2. 安装 Python 依赖

```bash
/opt/homebrew/bin/pip3.11 install openai-whisper python-telegram-bot ffmpeg-python dashscope mcp tqdm
```

### 3. 安装 douyin-mcp-server

```bash
git clone https://github.com/yzfly/douyin-mcp-server.git ~/douyin-mcp-server
cd ~/douyin-mcp-server
uv sync --python 3.11
```

### 4. 安装本地 AI 模型

```bash
brew services start ollama
ollama pull qwen2.5:7b
```

### 5. 配置 Telegram Bot

1. 找 **@BotFather** 创建 bot，保存 Token
2. `/setprivacy` → 选 bot → `Disable` — 禁用隐私模式，让 bot 可以读取群里所有消息
3. 确认群组功能已开启（Groups enabled），这样才能把 bot 加入群组

> **说明：** Privacy mode 设为 Disabled 后，bot 拥有全量读取权限，可以抓取聊天窗口中所有文本，不需要被 @ 才能响应。

### 6. 配置 Cookie（下载其他平台视频需要）

**X/Twitter：**
```bash
printf '# Netscape HTTP Cookie File\n.x.com\tTRUE\t/\tTRUE\t2147483647\tauth_token\t你的auth_token\n.x.com\tTRUE\t/\tTRUE\t2147483647\tct0\t你的ct0\n' > ~/x-cookies.txt
```

> 在浏览器 F12 → Application → Cookies → x.com 里找 auth_token 和 ct0

### 7. 配置并启动

编辑 `bot.py`，填入：
- `BOT_TOKEN` — 你的 Telegram Bot Token
- `ALLOWED_USER` — 你的 Telegram 用户 ID
- `ALLOWED_GROUP` — 允许响应的群 ID

```bash
mkdir -p ~/douyin-bot
cp bot.py ~/douyin-bot/bot.py
/opt/homebrew/bin/python3.11 ~/douyin-bot/bot.py
```

> **如果运行失败**，检查 `bot.py` 里的路径是否与实际文件位置一致，修改后重新运行即可。

---

### 🌏 国内用户额外说明

Telegram 在中国大陆被封锁，Bot 需要连接 `api.telegram.org`，**必须配置代理才能正常运行**。

如果使用虚拟环境安装的依赖，启动方式改为：

```bash
source ~/douyin-mcp-server/venv/bin/activate
python3 ~/douyin-bot/bot.py
```

---

## 📱 支持平台

| 平台 | 视频 | 文案 | 需要 Cookie |
|------|------|------|------------|
| 抖音 | ✅ | ✅ | ❌ 无需登录 |
| TikTok | ✅ | ✅ | ❌ |
| X/Twitter | ✅ | ✅ 推文原文 | ✅ 需要 |
| YouTube | ✅ | ✅ | ❌ |
| B站 | ✅ | ✅ | ❌ |
| Instagram | ✅ | ✅ | ✅ 需要 |
| 微博 | ✅ | ✅ | ❌ |
| 快手 | ✅ | ✅ | ❌ |
| 小红书图文 | ❌ | ❌ | ✅ 需要 |

---

## ⚠️ 注意事项

- 视频不自动删除，需手动清理 `~/Downloads/抖音/`
- 文案超过800字自动触发 AI 梳理
- 抖音无需登录可以直接下载视频、提取文案
- Instagram、小红书、X 等平台需要配置 cookie 才能下载
- 视频超过 50MB 会自动压缩后发送（上限 200MB），超过 200MB 提示本地路径手动提取
- 图文内容需要 cookie 才能自动提取，未配置时请手动保存图片
- Whisper 首次运行会下载模型约 150MB
- 10分钟视频处理约需 15-20 分钟，请耐心等待
- Bot 需保持 Mac 开机且终端运行
- Telegram 保留24小时内未读消息，重启后会自动补处理

---

## ⚙️ 开机自启

```bash
cat > ~/Library/LaunchAgents/com.douyin.bot.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.douyin.bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3.11</string>
        <string>/Users/你的用户名/douyin-bot/bot.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/douyin-bot.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/douyin-bot-error.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.douyin.bot.plist
```

> 记得把 `/Users/你的用户名/douyin-bot/bot.py` 改成你实际的文件路径。

---

## 📜 更新日志

### 2026-04-22
- 🔧 **抖音提取自动重试** — 网络抖动不再直接失败，自动重试 3 次（递增等待 2s→4s），长时间挂机更稳定
- 🆕 **超 50MB 视频自动压缩** — 50~200MB 视频用 ffmpeg 自动压缩到 50MB 以内再发送，超过 200MB 才提示手动提取
- 🔧 **抖音 MCP 请求加 timeout** — 防止网络挂起时无限阻塞，提取页面 15s / 下载视频 60s 超时

### 2026-04-16
- 🆕 **任意文章链接自动截图** — 非视频平台链接自动走 playwright 本地截图，图片+标题+原链接一起发出
- 🆕 **X 文章自动提取** — 隐藏侧栏/登录弹窗，分段滚动截图，内容清晰不压糊
- 🆕 **X/微博视频下载失败自动回退** — 纯文字/图片推文也能通过截图方式发送
- 🔧 **截图体验优化** — 滚动分段截图 + 高 DPR（1200×1600 @2x），发 Telegram 相册更清晰
- 🔧 **图片尺寸规范化（Pillow）** — 单边 >8000px 自动缩放、宽高比 >18:1 自动切分，修复 `Photo_invalid_dimensions`
- 🐛 **修复 whisper 幻觉** — 双层防护：
  - 参数层：`--condition_on_previous_text False`、提高 `--no_speech_threshold` 等
  - 后处理层：清理尾部俄/韩/日/阿/泰/希腊字符混杂的乱码行

### 2026-04-08
- 🆕 **抖音图文笔记提取** — 无需登录直接提取图文笔记的多张图片，作为相册发送
- 🆕 **bad.news 成人内容支持** — 通过 cookies 抓取视频，跳过 whisper 转录直发
- 🔧 **文案发送策略优化** — 视频 caption 随视频发送，超长文案分条发送
- 🐛 修复：caption 截断时保留末尾原链接
- 🐛 修复：whisper 显式指定 turbo 模型，避免回落到默认 small

### 2026-04-03
- 🎉 **项目首次发布**
- 抖音、X/Twitter、YouTube、B站 等多平台视频下载与文案提取
- 集成 Whisper 本地语音转文字
- 集成 Ollama + qwen2.5:7b 本地 AI 文案梳理
- Telegram Bot 白名单保护

---

## ⚠️ 免责声明

本项目仅供学习和个人使用，请遵守相关平台服务条款及当地法律法规。
