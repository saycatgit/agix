"""supports_vision + 图片渲染全链路单元测试
运行: cd src && python3 test_vision_integration.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as config_mod
from event_queue_manager import EventQueueManager
from flet_ui.chat_panel import ChatPanel
import flet as ft


class _MsgStyle:
    USER = "user"
    ASSISTANT = "assistant"
    ASK = "ask"


class _MsgType:
    ASK = "ask"
    DISPLAY = "display"


class _Page:
    def run_task(self, *a, **k):
        pass

    async def launch_url(self, *a, **k):
        pass


class _EQM:
    pass


class _Agent:
    def __init__(self):
        self.config = _Cfg()


class _Cfg:
    llm_list = []
    llm = None
    paths = None

    def __init__(self):
        self.paths = _Paths()
        self.llm = config_mod.LLMConfig()


class _Paths:
    current_work_dir = "/tmp"


def make_panel() -> ChatPanel:
    visuals = {
        "user": {"bg": ft.Colors.BLUE_50},
        "assistant": {"bg": ft.Colors.GREY_100},
        "ask": {"bg": ft.Colors.INDIGO_50},
    }
    avatars = {
        "user": ("U", ft.Colors.BLUE),
        "assistant": ("A", ft.Colors.GREY),
        "ask": ("?", None),
    }
    return ChatPanel(_Page(), _EQM(), _Agent(), visuals, avatars, _MsgStyle, _MsgType, {})


def test_switch_llm_syncs_supports_vision():
    cfg = config_mod.AppConfig()
    cfg.llm_list = [
        {"provider": "a", "model": "m1", "api_key": "sk-x", "active": True, "supports_vision": True},
        {"provider": "a", "model": "m2", "api_key": "sk-y", "active": False, "supports_vision": False},
    ]
    cfg.switch_llm(0)
    assert cfg.llm.supports_vision is True
    cfg.switch_llm(1)
    assert cfg.llm.supports_vision is False


def test_send_display_carries_images():
    eqm = EventQueueManager()
    eqm.send_display("hello", mode="chat", style=_MsgStyle.USER, images=["b64aaa", "b64bbb"])
    msg = eqm.chat_display_queue.get()
    assert msg.get("images") == ["b64aaa", "b64bbb"]
    eqm.send_display("plain", mode="chat")
    msg2 = eqm.chat_display_queue.get()
    assert "images" not in msg2


def test_add_message_renders_images():
    panel = make_panel()
    panel.add_message({"content": "hi", "style": "user", "message_type": "display", "images": ["b64img"]})
    row = panel._cl.controls[-1]
    bubble = row.controls[0].controls[0]
    col = bubble.content
    assert isinstance(col, ft.Column)
    assert len(col.controls) == 2  # markdown + images row
    img_row = col.controls[1]
    assert isinstance(img_row, ft.Row)
    img = img_row.controls[0]
    assert isinstance(img, ft.Image)
    assert img.src == "b64img"
    assert img.width == 180 and img.height == 180


def test_add_message_without_images():
    panel = make_panel()
    panel.add_message({"content": "hi", "style": "user", "message_type": "display"})
    row = panel._cl.controls[-1]
    bubble = row.controls[0].controls[0]
    col = bubble.content
    assert len(col.controls) == 1  # 只有 markdown


def test_image_btn_visible_follows_llm_vision():
    panel = make_panel()
    cfg = config_mod.AppConfig()
    cfg.llm_list = [
        {"provider": "a", "model": "m1", "api_key": "sk-x", "active": True, "supports_vision": True},
        {"provider": "a", "model": "m2", "api_key": "sk-y", "active": False, "supports_vision": False},
    ]
    # 按钮内联在输入 Row（input, image_btn, action_btn），非 suffix
    row = panel._cp.controls[4].content
    assert row.controls[1] is panel._image_btn
    cfg.switch_llm(0)
    panel.agent.config = cfg
    panel._update_image_btn_visibility()
    assert panel._image_btn.visible is True
    cfg.switch_llm(1)
    panel._update_image_btn_visibility()
    assert panel._image_btn.visible is False


if __name__ == "__main__":
    test_switch_llm_syncs_supports_vision()
    test_send_display_carries_images()
    test_add_message_renders_images()
    test_add_message_without_images()
    test_image_btn_visible_follows_llm_vision()
    print("OK")
