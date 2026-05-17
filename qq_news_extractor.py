"""腾讯新闻视频提取器
news.qq.com / view.inews.qq.com 的视频是 JS 动态加载的 m3u8 流，
yt-dlp 不支持。这里用 Playwright 拦截 m3u8 请求，再交给 ffmpeg 下载。
"""
import asyncio
import os
import subprocess
from typing import Optional
from playwright.async_api import async_playwright

QQ_NEWS_HOSTS = ("news.qq.com", "view.inews.qq.com", "inews.qq.com")
M3U8_KEYS = (".m3u8",)
NAV_TIMEOUT_MS = 30000
EXTRA_WAIT_MS = 6000


def is_qq_news(url: str) -> bool:
    return any(h in url for h in QQ_NEWS_HOSTS)


async def fetch_m3u8(url: str) -> Optional[str]:
    """打开页面，拦截到第一条 m3u8 链接就返回。"""
    found: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
                )
            )
            page = await ctx.new_page()

            def on_request(req):
                u = req.url
                if any(k in u for k in M3U8_KEYS) and not found:
                    found.append(u)

            page.on("request", on_request)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            except Exception:
                pass
            for _ in range(EXTRA_WAIT_MS // 500):
                if found:
                    break
                await page.wait_for_timeout(500)
        finally:
            await browser.close()

    return found[0] if found else None


def download_m3u8(m3u8_url: str, out_path: str) -> bool:
    """ffmpeg 拉取 m3u8 流，转封装为 mp4，不重新编码。"""
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", m3u8_url, "-c", "copy",
         "-bsf:a", "aac_adtstoasc", out_path],
        capture_output=True, text=True, timeout=300
    )
    return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0


async def download_qq_news_video(url: str, out_path: str) -> bool:
    """完整流程：拦截 m3u8 → ffmpeg 下载 mp4。返回是否成功。"""
    m3u8 = await fetch_m3u8(url)
    if not m3u8:
        return False
    return await asyncio.get_event_loop().run_in_executor(
        None, download_m3u8, m3u8, out_path
    )
