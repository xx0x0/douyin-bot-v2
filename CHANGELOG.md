# 更新日志

本文件记录 douyin-bot 的重要变更。日期格式 YYYY-MM-DD。

## 2026-05-14 ~ 05-18

### 纯视频平台失败时静默（2026-05-18）

YouTube / Bilibili / Instagram / 快手 / 小红书 这类纯视频站点，下载失败时不再响应任何错误消息或截图，直接静默跳过。
原因：这些站点没有"图文推文"形态，下载失败基本意味着原视频被删/区域限制/付费墙，截图也没意义。
保留的兜底逻辑：X / weibo / 腾讯新闻等带文字内容的站点，视频失败时仍走截图。

### 腾讯新闻视频下载（2026-05-17）

新增 `qq_news_extractor.py`：用 Playwright 拦截页面里的 m3u8 流，再用 ffmpeg 转封装为 mp4。
- 触发：`news.qq.com` / `view.inews.qq.com`
- 流程：访问页面 → 拦截首个 m3u8 请求（最多等 6 秒）→ ffmpeg `-c copy` 转 mp4
- 失败兜底：拦截不到 m3u8 或 ffmpeg 报错 → 自动回退到截图

原因：yt-dlp 不支持腾讯新闻（页面视频是 JS 动态加载的 blob），且 yt-dlp 的 vqq:video extractor 当前被腾讯反爬限制。

### 未知链接智能分流（2026-05-17）

未知链接（不在 PLATFORMS 列表）的处理逻辑改为：
1. 白名单文章平台（X/微博/微信公众号/知乎/Medium/Substack）→ 直接截图
2. 其他链接 → 用 `yt-dlp --simulate` 探测 10 秒
   - 探测到视频 → 走视频下载流程
   - 没有视频或超时 → 截图
3. 视频下载失败 → 自动回退到截图（之前只对 X/weibo 兜底，现扩展到所有平台）

### 口令控制

消息里可在链接前后任意位置加口令：

- `/skip` 或 `跳过` → 直接忽略，不处理
- `/title` 或 `标题` → 只发视频+标题，跳过 whisper
- `/text` 或 `文案` → 只提取文案，不发视频

### 启动通知

bot 启动时自动给 BOT_OWNER 发一条启动消息，列出支持的口令。新增 `BOT_OWNER` 环境变量（不填则取 ALLOWED_USERS 最小值）。

### whisper 幻觉处理升级

- `clean_hallucination` 新增全局占比检测：幻觉行超过 50% 或超过 20 行直接返回空，解决从头就乱的情况（之前只裁尾部）
- 新增常见幻觉短语黑名单（"优优独播剧场"、"字幕志愿者"等）

### whisper 前置试探扩展到所有平台

之前只有 X/Twitter 才截前 10 秒试探，现在所有平台统一截前 15 秒跑 whisper，不连贯直接跳过全程转录，节省时间。

### 文章链接逻辑收紧

`is_article_url` 改为白名单逻辑，只有明确列出的文章平台（twitter.com、x.com、weibo.com 等）才走截图流程，其余未知链接一律忽略不响应。

### github.com 加入平台列表

github.com 链接现在走文章截图流程（之前因不在平台列表被当作未知链接处理）。

## 2026-04-29

### 仓库可直接 clone 启动

- 新增 `run.sh`（启动脚本，加载 `.env` 后跑 bot.py）入库
- 新增 `.env.example`（环境变量模板）入库
- `.gitignore` 追加 `*.log`（避免 `bot.log` 入库）
- README.md 启动章节改写：从「编辑 bot.py 填值 + python3 bot.py」改为「复制 .env.example → .env 填值 + ./run.sh」，与代码实际行为一致

### 白名单扩展：支持多用户 + 多群组

**变更：** 把白名单从「单用户 + 单群」改成「多用户 + 多群」，配置项继续叫 `ALLOWED_USER` / `ALLOWED_GROUP`，但值用逗号分隔。

**.env：** `ALLOWED_USER` 扩展为多个用户 ID（逗号分隔），`ALLOWED_GROUP` 扩展为多个群 ID（逗号分隔）。具体值见本地 `.env`（不入库）。

**bot.py：**
- `ALLOWED_USER` → `ALLOWED_USERS`（set），`ALLOWED_GROUP` → `ALLOWED_GROUPS`（set）
- 白名单判断改为 `chat_id not in ALLOWED_GROUPS and user.id not in ALLOWED_USERS`

**README.md：** 同步说明配置项现支持逗号分隔多个 ID。

**注意事项：**
- 改完后需重启 bot 进程才生效
- Telegram 每个 bot token 只允许一个 `getUpdates` 轮询客户端，重启时务必先停旧进程，避免双开导致 `Conflict: terminated by other getUpdates request` 报错
