"""Playwright 验证 Flet Web 客户端是否响应 TextField.suffix 运行时更新。

流程：截图A(无suffix, 按钮OFF) → 点击TOGGLE → 截图B(有suffix, 按钮ON) → 再点 → 截图C。
判定逻辑：
  - 按钮文字区 A→B 变化 → WebSocket 同步正常（排除连接问题）
  - suffix 区域 A→B、B→C 变化且 A→C 不变 → 客户端支持动态更新
  - suffix 区域三者均不变 → 客户端不支持
"""
import io
import sys
import time

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8599"
# TextField 宽400、padding 10，suffix 图标位于输入框内部右侧
SUFFIX_BOX = (345, 15, 400, 52)  # x0,y0,x1,y1
BTN_BOX = (10, 76, 110, 116)    # 按钮文字区域（验证WebSocket同步）
TOGGLE_POS = (70, 96)           # Toggle 按钮中心（坐标点击）


def region_diff(png_a: bytes, png_b: bytes, box) -> int:
    ia = Image.open(io.BytesIO(png_a)).convert("RGB").crop(box)
    ib = Image.open(io.BytesIO(png_b)).convert("RGB").crop(box)
    pa, pb = ia.load(), ib.load()
    total = 0
    w, h = ia.size
    for y in range(h):
        for x in range(w):
            ra, ga, ba = pa[x, y]
            rb, gb, bb = pb[x, y]
            total += abs(ra - rb) + abs(ga - gb) + abs(bb - ba)
    return total


def full_diff(png_a: bytes, png_b: bytes) -> int:
    ia = Image.open(io.BytesIO(png_a)).convert("RGB")
    ib = Image.open(io.BytesIO(png_b)).convert("RGB")
    pa, pb = ia.load(), ib.load()
    total = 0
    w, h = ia.size
    for y in range(h):
        for x in range(w):
            ra, ga, ba = pa[x, y]
            rb, gb, bb = pb[x, y]
            total += abs(ra - rb) + abs(ga - gb) + abs(bb - ba)
    return total


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-gpu"],
        )
        page = browser.new_page(viewport={"width": 800, "height": 500})
        page.goto(URL, wait_until="load", timeout=30000)
        for _ in range(30):
            try:
                page.wait_for_selector("canvas", timeout=2000)
                break
            except Exception:
                time.sleep(1)
        time.sleep(12)  # 等 Flutter 首帧渲染稳定

        shot_a = page.screenshot()
        open("/tmp/shot_a.png", "wb").write(shot_a)
        page.mouse.click(*TOGGLE_POS)
        time.sleep(0.3)
        shot_ink = page.screenshot()  # 捕捉点击水波纹，验证点击已生效
        time.sleep(2)
        shot_b = page.screenshot()
        open("/tmp/shot_b.png", "wb").write(shot_b)
        page.mouse.click(*TOGGLE_POS)
        time.sleep(2)
        shot_c = page.screenshot()
        open("/tmp/shot_c.png", "wb").write(shot_c)

        d_ab = region_diff(shot_a, shot_b, SUFFIX_BOX)
        d_bc = region_diff(shot_b, shot_c, SUFFIX_BOX)
        d_ac = region_diff(shot_a, shot_c, SUFFIX_BOX)
        btn_ab = region_diff(shot_a, shot_b, BTN_BOX)
        f_ink = full_diff(shot_a, shot_ink)
        f_ab = full_diff(shot_a, shot_b)

        print(f"FULL DIFF A->ink(点击瞬间): {f_ink}")
        print(f"FULL DIFF A->B: {f_ab}")
        print(f"BTN DIFF A->B (OFF→ON): {btn_ab}")
        print(f"SUFFIX DIFF A->B (无→有): {d_ab}")
        print(f"SUFFIX DIFF B->C (有→无): {d_bc}")
        print(f"SUFFIX DIFF A->C (无→无): {d_ac}")

        threshold = 3000
        if d_ab > threshold and d_bc > threshold and d_ac <= threshold:
            print("RESULT: 客户端支持运行时修改 TextField.suffix ✅")
        else:
            print("RESULT: 客户端不支持运行时修改 TextField.suffix ❌")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
