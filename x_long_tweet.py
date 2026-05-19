"""X (Twitter) 长推文（NoteTweet）全文提取
yt-dlp 的 X extractor 只能拿到 280 字内的 description（X Premium 长推文被截断）。
这个模块用 syndication API 探测是否为长推，是的话用 Playwright 抓完整正文。
"""
import asyncio
import json
import os
import re
import urllib.request
from typing import Optional


SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result?id={tid}&token=4c2mmul6mnu"


def _extract_tweet_id(url: str) -> Optional[str]:
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None


def is_long_tweet(url: str) -> bool:
    """通过 syndication API 探测是否长推。失败时保守返回 False。"""
    tid = _extract_tweet_id(url)
    if not tid:
        return False
    try:
        req = urllib.request.Request(
            SYNDICATION_URL.format(tid=tid),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return bool(data.get("note_tweet"))
    except Exception:
        return False


def _load_x_cookies() -> list:
    """读取 ~/x-cookies.txt（Netscape 格式），转成 Playwright cookies。"""
    path = os.path.expanduser("~/x-cookies.txt")
    if not os.path.exists(path):
        return []
    cookies = []
    with open(path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) < 7:
                continue
            cookies.append({
                "name": parts[5],
                "value": parts[6],
                "domain": parts[0],
                "path": parts[2],
                "secure": parts[3] == "TRUE",
                "httpOnly": False,
                "expires": int(parts[4]) if parts[4].lstrip("-").isdigit() else -1,
            })
    return cookies


async def fetch_full_tweet_text(url: str, timeout_ms: int = 30000) -> Optional[str]:
    """打开 X 单推页面，点击 Show more，提取主推 article 的完整 innerText。
    会把内嵌 a 标签替换成展开 URL 文本。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                )
            )
            cookies = _load_x_cookies()
            if cookies:
                await ctx.add_cookies(cookies)
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:
                pass
            await page.wait_for_timeout(3000)

            for sel in [
                'div[data-testid="tweet-text-show-more-link"]',
                'button:has-text("Show more")',
                'button:has-text("显示更多")',
            ]:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass

            text = await page.evaluate("""() => {
                const a = document.querySelectorAll('article[data-testid="tweet"]')[0];
                if (!a) return null;
                const tt = a.querySelector('[data-testid="tweetText"]');
                if (!tt) return null;
                const clone = tt.cloneNode(true);
                clone.querySelectorAll('a').forEach(link => {
                    const span = document.createElement('span');
                    span.textContent = link.textContent.replace(/…$/, '');
                    link.replaceWith(span);
                });
                return clone.innerText;
            }""")
            return text.strip() if text else None
        finally:
            await browser.close()
