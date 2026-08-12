"""agix_web_e2e_probe.py — 8502 真实应用端到端联调验证脚本。
流程：打开页面 → 等待 canvas → 截图（默认模型 deepseek-v4-flash, vision=False 按钮应隐藏）。
用法: /home/myenv/bin/python agix_web_e2e_probe.py
"""
import sys, time
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8502"

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome",
                              args=["--no-sandbox", "--disable-gpu"])
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        pg.goto(URL, wait_until="load", timeout=30000)
        for _ in range(60):
            try:
                pg.wait_for_selector("canvas", timeout=2000)
                break
            except Exception:
                time.sleep(1)
        time.sleep(12)
        pg.screenshot(path="/tmp/agix_e2e_1.png")
        b.close()
    print("截图完成: /tmp/agix_e2e_1.png")

if __name__ == "__main__":
    main()
