"""flet_visible_probe_client.py — v10 客户端验证脚本。

流程：截图A → 点击TOGGLE(65,157) → 截图B → 点击TOGGLE → 截图C。
区域（v10 布局：Row=[TextField(400), image_btn, SEND]，第二行TOGGLE）：
- IMG_BOX: image_btn 区域 x≈410-480, y≈40-100（图标+按钮）
- STATE_BOX: state_text 区域 (5,5,120,30)
- BTN_BOX: TOGGLE 按钮区域 (5,135,130,180)
判定：IMG A→B、B→C 均 > 阈值且 A→C ≤ 阈值 → Row visible 双向支持。
"""
import time
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8599"
TOGGLE_POS = (65, 125)
IMG_BOX = (405, 40, 500, 90)
STATE_BOX = (5, 5, 120, 30)
BTN_BOX = (5, 135, 130, 180)
THRESHOLD = 3000


def crop_diff(img, box):
    px = img.load()
    x0, y0, x1, y1 = box
    cnt = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if abs(r - 248) + abs(g - 249) + abs(b - 255) > 30:
                cnt += 1
    return cnt


def diff(im1, im2, box):
    p1, p2 = im1.load(), im2.load()
    x0, y0, x1, y1 = box
    cnt = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if p1[x, y] != p2[x, y]:
                cnt += 1
    return cnt


def main():
    from PIL import Image
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome",
                              args=["--no-sandbox", "--disable-gpu"])
        pg = b.new_page(viewport={"width": 800, "height": 500})
        pg.goto(URL, wait_until="load", timeout=30000)
        for _ in range(40):
            try:
                pg.wait_for_selector("canvas", timeout=2000)
                break
            except Exception:
                time.sleep(1)
        time.sleep(10)
        pg.screenshot(path="/tmp/v10_a.png")
        pg.mouse.click(*TOGGLE_POS)
        time.sleep(0.3)
        pg.screenshot(path="/tmp/v10_ink1.png")
        time.sleep(2)
        pg.screenshot(path="/tmp/v10_b.png")
        pg.mouse.click(*TOGGLE_POS)
        time.sleep(0.3)
        pg.screenshot(path="/tmp/v10_ink2.png")
        time.sleep(2)
        pg.screenshot(path="/tmp/v10_c.png")
        b.close()

    a = Image.open("/tmp/v10_a.png").convert("RGB")
    ink1 = Image.open("/tmp/v10_ink1.png").convert("RGB")
    ink2 = Image.open("/tmp/v10_ink2.png").convert("RGB")
    bb = Image.open("/tmp/v10_b.png").convert("RGB")
    cc = Image.open("/tmp/v10_c.png").convert("RGB")

    print(f"FULL DIFF A->ink1: {diff(a, ink1, (0, 0, 800, 500))}  B->ink2: {diff(bb, ink2, (0, 0, 800, 500))}")
    print(f"STATE DIFF A->B: {diff(a, bb, STATE_BOX)}  B->C: {diff(bb, cc, STATE_BOX)}")
    print(f"BTN  DIFF A->B: {diff(a, bb, BTN_BOX)}  B->C: {diff(bb, cc, BTN_BOX)}")
    d_ab = diff(a, bb, IMG_BOX)
    d_bc = diff(bb, cc, IMG_BOX)
    d_ac = diff(a, cc, IMG_BOX)
    print(f"IMG  DIFF A->B (显示→隐藏): {d_ab}")
    print(f"IMG  DIFF B->C (隐藏→显示): {d_bc}")
    print(f"IMG  DIFF A->C (显示→显示): {d_ac}")
    ink_ok = diff(a, ink1, (0, 0, 800, 500)) > 10000 and diff(bb, ink2, (0, 0, 800, 500)) > 10000
    hit_ok = diff(a, ink1, (0, 0, 800, 500)) > 10000 and diff(bb, ink2, (0, 0, 800, 500)) > 10000
    if d_ab > THRESHOLD and d_bc > THRESHOLD and d_ac <= THRESHOLD and ink_ok and hit_ok:
        print("RESULT: Row 布局下 visible 双向切换支持 ✅")
    elif d_ab > THRESHOLD and d_bc <= THRESHOLD and d_ac > THRESHOLD:
        print("RESULT: visible 仅单向（隐藏后无法恢复）❌")
    else:
        print("RESULT: 未命中/异常，需人工检查截图")


if __name__ == "__main__":
    main()
