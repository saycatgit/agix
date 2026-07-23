"""关于面板 UI 组件"""

import flet as ft


class AboutPanel:
    """关于面板 —— 展示 Agix 基本信息"""

    TITLE_TEXT: str = "ℹ️ 关于"

    def __init__(self, page: ft.Page):
        self.page = page
        self._build()

    def _build(self):
        self._content_body = ft.Column([
            ft.Text("Agix", size=28, weight=ft.FontWeight.W_700),
            ft.Text("全能型 AI 个人助理", size=14, color=ft.Colors.GREY_500),
            ft.Divider(height=24, color=ft.Colors.GREY_300),
            ft.Text("Agix 是一款集成 LLM 的桌面端 AI 工作台，支持多供应商模型切换、"
                    "SSH 远程连接管理、定时/周期任务编排等能力。"
                    "可辅助开发者完成代码生成、项目维护、系统运维等工程任务，"
                    "致力于成为开发者日常工作中高效、可靠的 AI 伙伴。",
                    size=13, color=ft.Colors.GREY_700),
            ft.Divider(height=24, color=ft.Colors.GREY_300),
            ft.Text("版本号", size=14, weight=ft.FontWeight.W_600),
            ft.Text("v0.1.0", size=13, color=ft.Colors.GREY_700),
            ft.Divider(height=24, color=ft.Colors.GREY_300),
            ft.Text("联系我们", size=14, weight=ft.FontWeight.W_600),
            ft.Text("如有问题或建议，欢迎通过以下方式反馈：", size=13, color=ft.Colors.GREY_500),
            ft.Text("📧 邮箱：542628028@qq.com", size=13, color=ft.Colors.GREY_700),
            ft.Text("💬 社区：github.com/agix-ai/agix/discussions", size=13, color=ft.Colors.GREY_700),
        ], spacing=12, expand=True)

    @property
    def content_body(self) -> ft.Column:
        return self._content_body
