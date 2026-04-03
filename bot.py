#!/usr/bin/env python3
import subprocess, os, sys, json, re, requests, glob
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "YOUR_BOT_TOKEN"
SAVE_DIR = os.path.expanduser("~/Downloads/抖音")
DOUYIN_MCP = os.path.expanduser("~/douyin-mcp-server")
os.makedirs(SAVE_DIR, exist_ok=True)

# 白名单：只响应指定用户私聊 + 指定群
ALLOWED_USER = 12345678         # 替换成你的 Telegram 用户 ID
ALLOWED_GROUP = -1001234567890  # 替换成你的群 ID

sys.path.insert(0, DOUYIN_MCP)
from douyin_mcp_server.server import get_douyin_download_link

def analyze_transcript(transcript, title):
    import urllib.request, json as _json
    prompt = f"""你是内容提炼助手，严格基于原文内容，按以下格式输出：

**🎯 核心结论**
用2-3句话说明最重要的观点。

**📊 关键数据/事实**
列出具体数字或事实（没有则跳过）

**✅ 可执行建议**
1. 具体行动，动词开头
2. 具体行动，动词开头
3. 具体行动，动词开头

**⚠️ 避坑提醒**
需要注意的事项

**💬 一句话带走**
最值得记住的一句话，不超过20字

标题：{title}
文案：{transcript}"""
    data = _json.dumps({"model": "qwen2.5:7b", "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return _json.loads(r.read()).get("response", "")
    except:
        return ""

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    # 白名单检查
    user = update.message.from_user
    chat_id = update.message.chat.id
    print(f"收到消息 - 用户：{user.username or user.first_name}（ID:{user.id}）群：{chat_id}")
    if chat_id != ALLOWED_GROUP and user.id != ALLOWED_USER:
        return

    raw = update.message.text.strip()

    # 从消息中提取链接
    url_match = re.search(r"https?://\S+", raw)
    if not url_match:
        return
    text = url_match.group(0).rstrip(".,)")

    PLATFORMS = ["douyin.com", "v.douyin.com", "tiktok.com", "xiaohongshu.com",
                 "xhslink.com", "twitter.com", "x.com", "youtube.com", "youtu.be",
                 "instagram.com", "weibo.com", "bilibili.com", "b23.tv", "kuaishou.com"]
    if not any(x in text for x in PLATFORMS):
        return

    # 解析短链接，去除追踪参数
    clean_url = text
    if "v.douyin.com" in text or "b23.tv" in text:
        try:
            r = requests.head(text, allow_redirects=True, timeout=10)
            real_url = r.url
            match = re.search(r"/video/(\d+)|/note/(\d+)", real_url)
            if match:
                vid = match.group(1) or match.group(2)
                path = "video" if match.group(1) else "note"
                clean_url = f"https://www.douyin.com/{path}/{vid}"
        except:
            pass

    # 图文提示
    if "/note/" in clean_url:
        await update.message.reply_text(
            "📸 这是图文内容，需要登录 cookie 才能自动提取，请手动保存图片\n\n🔗 " + clean_url
        )
        return

    await update.message.reply_text("⏬ 获取视频中...")

    video_path = f"{SAVE_DIR}/video_{abs(hash(clean_url))}.mp4"
    title = ""
    is_x = any(x in clean_url for x in ["twitter.com", "x.com"])
    is_douyin = any(x in clean_url for x in ["douyin.com", "v.douyin.com", "tiktok.com"])

    if is_douyin:
        try:
            result = get_douyin_download_link(clean_url)
            info = json.loads(result)
            video_url = info.get("video_url") or info.get("download_url") or info.get("url", "")
            title = info.get("title") or info.get("desc", "")
        except Exception as e:
            await update.message.reply_text(f"❌ 获取失败：{e}")
            return
        if not video_url:
            await update.message.reply_text("❌ 无法获取视频链接")
            return
        subprocess.run(["yt-dlp", "-o", video_path, video_url], capture_output=True)

    else:
        cookies = os.path.expanduser("~/x-cookies.txt")
        cookie_args = ["--cookies", cookies] if os.path.exists(cookies) else []

        # X 先获取推文文字
        if is_x:
            subprocess.run(
                ["yt-dlp", "--no-playlist", "--write-info-json", "--skip-download"]
                + cookie_args + ["-o", f"{SAVE_DIR}/xinfo", clean_url],
                capture_output=True
            )
            json_files = glob.glob(f"{SAVE_DIR}/xinfo*.json")
            if json_files:
                with open(json_files[0]) as f:
                    info = json.loads(f.read())
                title = info.get("description") or info.get("title", "")
                os.remove(json_files[0])

        dl = subprocess.run(
            ["yt-dlp", "--no-playlist"] + cookie_args + ["-o", video_path, clean_url],
            capture_output=True, text=True
        )
        if dl.returncode != 0:
            await update.message.reply_text(f"❌ 下载失败：{dl.stderr[-300:]}")
            return

    if not os.path.exists(video_path):
        await update.message.reply_text("❌ 视频下载失败")
        return

    # X：发视频 + 推文原文，不转文案
    if is_x:
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        if file_size <= 50:
            with open(video_path, "rb") as vf:
                await update.message.reply_video(video=vf)
        else:
            await update.message.reply_text(
                f"⚠️ 视频过大（{file_size:.1f}MB），超过 Telegram 50MB 限制，请到本地手动提取\n📁 {video_path}"
            )
        if title:
            await update.message.reply_text(f"📝 推文内容：\n\n{title}\n\n🔗：{clean_url}")
        return

    # 抖音和其他平台：先转文案，再发视频
    await update.message.reply_text("🎙️ 转文案中（需1-2分钟）...")
    subprocess.run(
        ["whisper", video_path, "--language", "zh",
         "--output_format", "txt", "--output_dir", SAVE_DIR],
        capture_output=True
    )

    txt_path = os.path.splitext(video_path)[0] + ".txt"
    transcript = ""
    if os.path.exists(txt_path):
        with open(txt_path) as f:
            transcript = f.read().strip()
        os.remove(txt_path)

    # 发视频（超过50MB提示手动提取）
    file_size = os.path.getsize(video_path) / (1024 * 1024)
    if file_size <= 50:
        with open(video_path, "rb") as vf:
            await update.message.reply_video(video=vf)
    else:
        await update.message.reply_text(
            f"⚠️ 视频过大（{file_size:.1f}MB），超过 Telegram 50MB 限制，请到本地手动提取\n📁 {video_path}"
        )

    if not transcript:
        await update.message.reply_text(f"❌ 文案提取失败\n\n原视频链接：{clean_url}")
        return

    # 发原文案（分段）
    header = f"视频标题：{title}\n\n文案：\n"
    footer = f"\n\n原视频链接：{clean_url}"
    full = header + transcript + footer
    if len(full) <= 4000:
        await update.message.reply_text(full)
    else:
        await update.message.reply_text(header + transcript[:3800])
        remaining = transcript[3800:]
        while remaining:
            await update.message.reply_text(remaining[:4000])
            remaining = remaining[4000:]
        await update.message.reply_text(footer.strip())

    # 超过800字才梳理
    if len(transcript) > 800:
        await update.message.reply_text("🤖 AI 梳理中...")
        analysis = analyze_transcript(transcript, title)
        if analysis:
            analysis_msg = f"视频标题：{title}\n\n梳理后的文案：\n\n{analysis}\n\n原视频链接：{clean_url}"
            await update.message.reply_text(analysis_msg[:4000] if len(analysis_msg) > 4000 else analysis_msg)
        else:
            await update.message.reply_text("⚠️ AI 梳理失败，请检查 Ollama 是否运行")

app = ApplicationBuilder().token(BOT_TOKEN).read_timeout(300).write_timeout(300).connect_timeout(300).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
print("✅ Bot 启动中...")
app.run_polling(drop_pending_updates=False)
