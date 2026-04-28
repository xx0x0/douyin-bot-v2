# 更新日志

本文件记录 douyin-bot 的重要变更。日期格式 YYYY-MM-DD。

## 2026-04-29

### 白名单扩展：支持多用户 + 多群组

**变更：** 把白名单从「单用户 + 单群」改成「多用户 + 多群」，配置项继续叫 `ALLOWED_USER` / `ALLOWED_GROUP`，但值用逗号分隔。

**.env：**
- `ALLOWED_USER` 增至 4 人：`***,***,***,***`
- `ALLOWED_GROUP` 增至 2 个群：`***,***`

**bot.py：**
- `ALLOWED_USER` → `ALLOWED_USERS`（set），`ALLOWED_GROUP` → `ALLOWED_GROUPS`（set）
- 白名单判断改为 `chat_id not in ALLOWED_GROUPS and user.id not in ALLOWED_USERS`

**README.md：** 同步说明配置项现支持逗号分隔多个 ID。

**注意事项：**
- 改完后需重启 bot 进程才生效
- Telegram 每个 bot token 只允许一个 `getUpdates` 轮询客户端，重启时务必先停旧进程，避免双开导致 `Conflict: terminated by other getUpdates request` 报错
