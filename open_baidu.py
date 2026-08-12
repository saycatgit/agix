#!/usr/bin/env python3
"""百度搜索「天气」，浏览器保持打开"""
import asyncio, sys
from playwright.async_api import async_playwright

async def main():
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/msedge_baidu_temp",
        channel="msedge",
        headless=False,
        args=["--no-sandbox", "--disable-gpu", "--disable-blink-features=AutomationControlled"],
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """)

    page = await context.new_page()
    await page.goto("https://www.baidu.com", wait_until="domcontentloaded")
    await asyncio.sleep(2)

    print(f"标题: {await page.title()}", flush=True)

    # JS 设值 + 触发回车搜索
    await page.evaluate('''() => {
        const kw = document.querySelector("#kw");
        const form = document.querySelector("#form");
        if (kw) {
            kw.value = "天气";
            kw.dispatchEvent(new Event("input", {bubbles: true}));
        }
        if (form) form.submit();
    }''')

    print("已提交搜索，等待结果...", flush=True)
    await asyncio.sleep(3)
    print(f"搜索后标题: {await page.title()}", flush=True)
    print("浏览器保持打开，按 Ctrl+C 退出...", flush=True)

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    await context.close()
    await pw.stop()

asyncio.run(main())
