#!/usr/bin/env python3
# 用法: python3 test_download.py <URL>
import sys, os, subprocess, glob, json, re, requests

SAVE_DIR = os.path.expanduser("~/Downloads/抖音")
os.makedirs(SAVE_DIR, exist_ok=True)

url = sys.argv[1] if len(sys.argv) > 1 else input("输入链接: ").strip()
print(f"[1] 测试 URL: {url}")

video_path = f"{SAVE_DIR}/test_video_{abs(hash(url))}.mp4"
cookies = os.path.expanduser("~/x-cookies.txt")
cookie_args = ["--cookies", cookies] if os.path.exists(cookies) else []
print(f"[2] cookies 文件: {'存在' if cookie_args else '不存在，不带 cookies'}")

# 获取 info
print("[3] 运行 yt-dlp 获取 info...")
r = subprocess.run(
    ["yt-dlp", "--no-playlist", "--write-info-json", "--skip-download"]
    + cookie_args + ["-o", f"{SAVE_DIR}/xinfo", url],
    capture_output=True, text=True
)
print(f"    返回码: {r.returncode}")
if r.stdout: print(f"    stdout: {r.stdout[-500:]}")
if r.stderr: print(f"    stderr: {r.stderr[-500:]}")

json_files = glob.glob(f"{SAVE_DIR}/xinfo*.json")
if json_files:
    with open(json_files[0]) as f:
        info = json.load(f)
    print(f"    title: {info.get('title','')[:80]}")
    os.remove(json_files[0])
else:
    print("    没有生成 info json")

# 下载视频
print("[4] 运行 yt-dlp 下载视频...")
r2 = subprocess.run(
    ["yt-dlp", "--no-playlist"] + cookie_args + ["-o", video_path, url],
    capture_output=True, text=True, timeout=120
)
print(f"    返回码: {r2.returncode}")
if r2.stdout: print(f"    stdout: {r2.stdout[-500:]}")
if r2.stderr: print(f"    stderr: {r2.stderr[-500:]}")

if os.path.exists(video_path):
    size = os.path.getsize(video_path) / 1024 / 1024
    print(f"[5] 视频已下载: {video_path} ({size:.1f} MB)")
else:
    print("[5] ❌ 视频文件不存在，下载失败")
    sys.exit(1)

# whisper
print("[6] 运行 whisper 转文案（可能需要1-2分钟）...")
r3 = subprocess.run(
    ["whisper", video_path, "--language", "zh",
     "--output_format", "txt", "--output_dir", SAVE_DIR],
    capture_output=True, text=True, timeout=300
)
print(f"    返回码: {r3.returncode}")
if r3.stderr: print(f"    stderr: {r3.stderr[-300:]}")

txt_path = os.path.splitext(video_path)[0] + ".txt"
if os.path.exists(txt_path):
    with open(txt_path) as f:
        transcript = f.read().strip()
    print(f"[7] 文案长度: {len(transcript)} 字")
    print(f"    前200字: {transcript[:200]}")
    os.remove(txt_path)
else:
    print("[7] ❌ 没有生成文案 txt")

print("\n✅ 测试完成")
