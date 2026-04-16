#!/usr/bin/env python3
import subprocess, os, sys, json, re, requests, glob
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from playwright.sync_api import sync_playwright
from PIL import Image

# 从环境变量读取（建议用 .env + 启动脚本注入）
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
# bad.news cookies（过期后从浏览器 cURL 重新复制）
BADNEWS_COOKIES = os.environ.get("BADNEWS_COOKIES", "")

SAVE_DIR = os.path.expanduser("~/Downloads/抖音")
DOUYIN_MCP = os.path.expanduser("~/douyin-mcp-server")
os.makedirs(SAVE_DIR, exist_ok=True)

# 白名单：只响应指定用户私聊 + 指定群
ALLOWED_USER = int(os.environ.get("ALLOWED_USER", "12345678"))         # 替换成你的 Telegram 用户 ID
ALLOWED_GROUP = int(os.environ.get("ALLOWED_GROUP", "-1001234567890")) # 替换成你的群 ID

sys.path.insert(0, DOUYIN_MCP)
from douyin_mcp_server.server import get_douyin_download_link

def webpage_screenshot(url, save_path_prefix, max_segments=8):
    """用 playwright 滚动分段截图，返回 (图片路径列表, 页面标题)

    每段一张 viewport 大小的清晰图，便于 Telegram 显示时不被压糊。
    X/Twitter 会额外隐藏侧栏和登录弹窗。
    """
    paths = []
    is_x = ("twitter.com" in url) or ("x.com" in url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1200, "height": 1600},
            device_scale_factor=2,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)
        title = page.title() or ""

        # 仅 X/Twitter：隐藏侧栏 + 登录弹窗，并强制允许滚动
        if is_x:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
            except Exception:
                pass
            page.add_style_tag(content="""
                [data-testid="sidebarColumn"],
                [data-testid="BottomBar"],
                [data-testid="sheetDialog"],
                [data-testid="mask"],
                [aria-label*="ign up" i],
                [aria-label*="og in" i],
                div[role="dialog"][aria-modal="true"] { display: none !important; }
                html, body { overflow: auto !important; height: auto !important; }
            """)
            try:
                page.locator('article[data-testid="tweet"]').first.wait_for(timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(800)

        # 滚动分段截图
        total_height = page.evaluate("document.body.scrollHeight")
        viewport_height = page.evaluate("window.innerHeight")
        step = max(viewport_height - 80, 600)
        segments = max(1, min(max_segments, (total_height + step - 1) // step))

        for i in range(segments):
            y = i * step
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(600)
            seg_path = f"{save_path_prefix}_{i+1}.png"
            page.screenshot(path=seg_path, full_page=False)
            paths.append(seg_path)

        browser.close()
    return paths, title


def is_article_url(url):
    """判断链接是否为文章（非视频/图文平台）"""
    VIDEO_HOSTS = [
        "douyin.com", "v.douyin.com", "tiktok.com", "xiaohongshu.com",
        "xhslink.com", "youtube.com", "youtu.be", "instagram.com",
        "bilibili.com", "b23.tv", "kuaishou.com", "bad.news",
    ]
    return not any(h in url for h in VIDEO_HOSTS)


def normalize_for_telegram(paths):
    """确保图片符合 Telegram 限制：宽高比 1:20~20:1、尺寸≤10000，超则切分/缩放。
    返回处理后的路径列表（可能比输入多）。
    """
    MAX_SIDE = 8000              # 单边像素上限（保守值）
    MAX_RATIO = 18               # 宽高比上限（保守值，实际 Telegram 是 20）
    TARGET_WIDTH = 1600          # 切分后每段目标宽度
    result = []
    for p in paths:
        try:
            img = Image.open(p)
            w, h = img.size
            # 先按单边上限整体缩放
            if max(w, h) > MAX_SIDE:
                scale = MAX_SIDE / max(w, h)
                w2, h2 = int(w * scale), int(h * scale)
                img = img.resize((w2, h2), Image.LANCZOS)
                img.save(p)
                w, h = w2, h2
            # 再查宽高比：太长就竖切成多段
            if h / max(w, 1) > MAX_RATIO:
                # 每段高度 = 宽度 × (MAX_RATIO - 2)，留余量
                seg_h = int(w * (MAX_RATIO - 3))
                n = (h + seg_h - 1) // seg_h
                base, ext = os.path.splitext(p)
                for i in range(n):
                    top = i * seg_h
                    bot = min(h, top + seg_h)
                    crop = img.crop((0, top, w, bot))
                    new_path = f"{base}_part{i+1}{ext}"
                    crop.save(new_path)
                    result.append(new_path)
                # 原图切分后删除
                try:
                    os.remove(p)
                except Exception:
                    pass
            else:
                result.append(p)
        except Exception as e:
            print(f"[图片规范化失败] {p}: {e}")
            result.append(p)
    return result


def clean_hallucination(text):
    """清理 whisper 尾部幻觉：逐行从末尾往前检查，
    中文比例过低 / 出现非中英文混杂（俄/韩/日/阿/泰/希腊等）的行，连同之后全部丢弃。
    """
    if not text:
        return text
    lines = [l for l in text.split("\n") if l.strip()]
    # 非中英/标点的"杂语言"字符范围
    foreign_pat = re.compile(
        r"[\u0400-\u04FF"   # 西里尔（俄语）
        r"\uAC00-\uD7AF"    # 韩语
        r"\u3040-\u30FF"    # 日语假名
        r"\u0600-\u06FF"    # 阿拉伯
        r"\u0E00-\u0E7F"    # 泰语
        r"\u0370-\u03FF"    # 希腊
        r"]"
    )
    cut_idx = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        zh = len(re.findall(r"[\u4e00-\u9fff]", line))
        total = len(line)
        has_foreign = bool(foreign_pat.search(line))
        # 这一行是幻觉特征：短 + 含异域字符，或 短 + 中文极少且有非中文字母
        if has_foreign:
            cut_idx = i
            continue
        # 一行极短且中文占比极低（纯符号/单字"对"/"是"反复）
        if total <= 8 and zh <= 2 and re.fullmatch(r"[\s\u4e00-\u9fffA-Za-z\.\?\!。？！，,…]+", line):
            # 连续极短无信息量行也去掉
            cut_idx = i
            continue
        break
    return "\n".join(lines[:cut_idx]).strip()


def is_coherent(text):
    """判断 whisper 转录是否有实质文字内容（排除成人内容音效）"""
    if not text or len(text.strip()) < 20:
        return False
    zh = len(re.findall(r'[\u4e00-\u9fff]', text))
    en_words = re.findall(r'[a-zA-Z]{3,}', text)
    return zh > 15 or len(en_words) > 5

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
        with urllib.request.urlopen(req, timeout=120) as r:
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
                 "instagram.com", "weibo.com", "bilibili.com", "b23.tv", "kuaishou.com",
                 "bad.news"]

    # 非视频平台链接 → 走文章截图流程
    if not any(x in text for x in PLATFORMS):
        if is_article_url(text):
            try:
                await _process_article(update, text)
            except Exception as e:
                print(f"[ERROR article] {e}")
                import traceback; traceback.print_exc()
                try:
                    await update.message.reply_text(f"❌ 文章截图失败：{e}")
                except:
                    pass
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

    try:
        await _process(update, clean_url)
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback; traceback.print_exc()
        try:
            await update.message.reply_text(f"❌ 出错了：{e}")
        except:
            pass

async def _process_article(update: Update, url: str):
    """文章链接：滚动分段截图，作为相册发送（更清晰）"""
    await update.message.reply_text("📸 正在截取网页...")
    prefix = f"{SAVE_DIR}/article_{abs(hash(url))}"
    import asyncio
    loop = asyncio.get_event_loop()
    paths, title = await loop.run_in_executor(None, webpage_screenshot, url, prefix)
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        await update.message.reply_text(f"❌ 截图失败\n🔗 {url}")
        return
    # 规范化尺寸，防止 Telegram Photo_invalid_dimensions
    paths = normalize_for_telegram(paths)

    caption = (f"{title}\n\n" if title else "") + f"🔗 {url}"
    caption = caption[:1024]

    # Telegram 相册每组最多 10 张
    try:
        # 读入所有图片字节
        photos = []
        for p in paths:
            with open(p, "rb") as f:
                photos.append(f.read())

        if len(photos) == 1:
            await update.message.reply_photo(photo=photos[0], caption=caption)
        else:
            # 分组发送（每组最多 10 张），caption 放最后一组最后一张
            CHUNK = 10
            groups = [photos[i:i + CHUNK] for i in range(0, len(photos), CHUNK)]
            for idx, group in enumerate(groups):
                media = [InputMediaPhoto(media=b) for b in group]
                if idx == len(groups) - 1:
                    media[-1] = InputMediaPhoto(media=group[-1], caption=caption)
                await update.message.reply_media_group(media=media)
    finally:
        for p in paths:
            try:
                os.remove(p)
            except Exception:
                pass


async def _process(update: Update, clean_url: str):
    # 图文提取
    if "/note/" in clean_url:
        await update.message.reply_text("⏳ 处理中，请稍候...")
        try:
            result = get_douyin_download_link(clean_url)
            info = json.loads(result)
            if info.get("status") == "error":
                await update.message.reply_text(f"❌ 提取失败：{info.get('error', '未知错误')}")
                return
            title = info.get("title", "")
            images = info.get("images", [])
            if not images:
                await update.message.reply_text(f"❌ 未能提取到图片，请手动保存\n🔗 {clean_url}")
                return
            caption_text = (f"{title}\n\n" if title else "") + f"🔗 {clean_url}"
            photo_data = []
            for img_url in images:
                try:
                    r = requests.get(img_url, timeout=30,
                                     headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X)"})
                    if r.status_code == 200:
                        photo_data.append(r.content)
                except Exception as img_e:
                    print(f"[图片下载失败] {img_url}: {img_e}")
            if not photo_data:
                await update.message.reply_text(f"❌ 未能下载到图片\n🔗 {clean_url}")
                return
            media_group = [InputMediaPhoto(media=d) for d in photo_data]
            media_group[-1] = InputMediaPhoto(media=photo_data[-1], caption=caption_text[:1024])
            await update.message.reply_media_group(media=media_group)
        except Exception as e:
            print(f"[ERROR 图文] {e}")
            await update.message.reply_text(f"❌ 图文提取失败：{e}\n🔗 {clean_url}")
        return

    # await update.message.reply_text("⏬ 获取视频中...")

    await update.message.reply_text("⏳ 处理中，请稍候...")

    video_path = f"{SAVE_DIR}/video_{abs(hash(clean_url))}.mp4"
    title = ""
    is_x = any(x in clean_url for x in ["twitter.com", "x.com"])
    is_douyin = any(x in clean_url for x in ["douyin.com", "v.douyin.com", "tiktok.com"])
    is_badnews = "bad.news" in clean_url

    if is_badnews:
        # 构造下载 URL
        dl_url = clean_url
        if "/ajax/topic/" not in clean_url:
            m = re.search(r'/topic/(\d+)', clean_url)
            if m:
                dl_url = f"https://bad.news/ajax/topic/{m.group(1)}/download"
        cookie_dict = {}
        for part in BADNEWS_COOKIES.split(';'):
            if '=' in part:
                k, v = part.strip().split('=', 1)
                cookie_dict[k.strip()] = v.strip()
        page_hdrs = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                     'referer': 'https://bad.news/'}
        dl_hdrs = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            resp = requests.get(dl_url, cookies=cookie_dict, headers=page_hdrs, timeout=30)
            vid_match = re.search(r'content="\d+;\s*URL=([^"]+)"', resp.text)
            if not vid_match:
                vid_match = re.search(r'href="(https://[^"]+\.mp4[^"]*)"', resp.text)
            if not vid_match:
                await update.message.reply_text("❌ 无法提取视频链接，cookies 可能已过期")
                return
            video_dl_url = vid_match.group(1)
            r2 = requests.get(video_dl_url, headers=dl_hdrs, stream=True, timeout=60)
            if r2.status_code != 200:
                await update.message.reply_text(f"❌ 视频下载失败：HTTP {r2.status_code}")
                return
            with open(video_path, 'wb') as f:
                for chunk in r2.iter_content(chunk_size=65536):
                    f.write(chunk)
        except Exception as e:
            await update.message.reply_text(f"❌ bad.news 下载失败：{e}")
            return

    elif is_douyin:
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
            # 下载失败（可能是纯文字/图片推文），回退到截图
            if is_x or "weibo.com" in clean_url:
                await _process_article(update, clean_url)
                return
            await update.message.reply_text(f"❌ 下载失败：{dl.stderr[-300:]}")
            return

    if not os.path.exists(video_path):
        await update.message.reply_text("❌ 视频下载失败")
        return

    # bad.news 是成人内容，跳过文案提取，直接发视频
    if is_badnews:
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        if file_size <= 50:
            import subprocess as sp
            probe = sp.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", video_path],
                           capture_output=True, text=True)
            w, h = 0, 0
            if probe.stdout.strip():
                parts = probe.stdout.strip().split(",")
                if len(parts) == 2:
                    w, h = int(parts[0]), int(parts[1])
            with open(video_path, "rb") as vf:
                await update.message.reply_video(video=vf, width=w or None, height=h or None, supports_streaming=True)
        else:
            await update.message.reply_text(
                f"⚠️ 视频过大（{file_size:.1f}MB），超过 Telegram 50MB 限制，请到本地手动提取\n📁 {video_path}"
            )
        return

    # 所有平台：先转文案，再发视频
    # X 链接：先截前10秒试探，是成人内容就跳过全程 whisper
    run_whisper = True
    if is_x:
        preview_path = video_path + "_preview.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-t", "10", "-vn", "-ar", "16000", "-ac", "1", preview_path],
            capture_output=True
        )
        preview_txt = ""
        if os.path.exists(preview_path):
            subprocess.run(
                ["whisper", preview_path, "--language", "zh",
                 "--output_format", "txt", "--output_dir", SAVE_DIR],
                capture_output=True
            )
            prev_txt_path = preview_path.replace(".wav", ".txt")
            if os.path.exists(prev_txt_path):
                with open(prev_txt_path) as f:
                    preview_txt = f.read().strip()
                os.remove(prev_txt_path)
            os.remove(preview_path)
        if not is_coherent(preview_txt):
            run_whisper = False

    if run_whisper:
        # await update.message.reply_text("🎙️ 转文案中（需1-2分钟）...")
        subprocess.run(
            ["whisper", video_path, "--language", "zh", "--model", "turbo",
             "--output_format", "txt", "--output_dir", SAVE_DIR,
             # 防幻觉参数
             "--condition_on_previous_text", "False",
             "--no_speech_threshold", "0.8",
             "--logprob_threshold", "-0.5",
             "--compression_ratio_threshold", "2.0"],
            capture_output=True
        )

    txt_path = os.path.splitext(video_path)[0] + ".txt"
    transcript = ""
    if os.path.exists(txt_path):
        with open(txt_path) as f:
            transcript = f.read().strip()
        transcript = clean_hallucination(transcript)
        os.remove(txt_path)

    file_size = os.path.getsize(video_path) / (1024 * 1024)

    # 超过800字才 AI 梳理：梳理后文案随视频发，原文案单独发
    need_analysis = bool(transcript) and len(transcript) > 800
    analysis = ""
    if need_analysis:
        analysis = analyze_transcript(transcript, title)

    title_prefix = f"视频标题：{title}\n\n" if title else ""
    url_suffix = f"\n\n🔗 {clean_url}"
    # caption 上限 1024，预留 url 位置，超长则截断正文
    max_body = 1024 - len(url_suffix)
    if need_analysis and analysis:
        body = title_prefix + f"梳理后的文案：\n\n{analysis}"
    elif transcript:
        body = title_prefix + f"文案：\n{transcript}"
    else:
        body = title_prefix.rstrip()
    if len(body) > max_body:
        body = body[:max_body - 1] + "…"
    vid_caption = body + url_suffix

    # 发视频
    if file_size <= 50:
        import subprocess as sp
        probe = sp.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", video_path],
                       capture_output=True, text=True)
        w, h = 0, 0
        if probe.stdout.strip():
            parts = probe.stdout.strip().split(",")
            if len(parts) == 2:
                w, h = int(parts[0]), int(parts[1])
        with open(video_path, "rb") as vf:
            await update.message.reply_video(video=vf, width=w or None, height=h or None,
                                              caption=vid_caption, supports_streaming=True)
    else:
        await update.message.reply_text(
            f"⚠️ 视频过大（{file_size:.1f}MB），超过 Telegram 50MB 限制，请到本地手动提取\n📁 {video_path}"
        )

    # 用了 AI 梳理：原文案单独发一条
    if need_analysis and analysis:
        full_text = title_prefix + f"原文案：\n{transcript}\n\n🔗 {clean_url}"
        while full_text:
            await update.message.reply_text(full_text[:4000])
            full_text = full_text[4000:]
    elif need_analysis and not analysis:
        # 梳理失败：回退发原文案
        await update.message.reply_text("⚠️ AI 梳理失败，请检查 Ollama 是否运行")
        full_text = title_prefix + f"文案：\n{transcript}\n\n🔗 {clean_url}"
        while full_text:
            await update.message.reply_text(full_text[:4000])
            full_text = full_text[4000:]

app = ApplicationBuilder().token(BOT_TOKEN).read_timeout(300).write_timeout(300).connect_timeout(300).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
print("✅ Bot 启动中...")
app.run_polling(drop_pending_updates=False)
