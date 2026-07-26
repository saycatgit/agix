"""连接管理面板 UI 组件 —— SSH管理 + MCP 服务器"""

import asyncio, json, os, shutil, subprocess
import flet as ft


class ConnectionSettingsPanel:
    """连接管理面板：SSH密钥管理 + 当前SSH列表 + MCP 可用服务器"""

    PANEL_BGCOLOR = ft.Colors.WHITE
    LABEL_COLOR = ft.Colors.GREY_700
    TITLE_TEXT: str = "🔗 连接管理"

    TF_DEFAULTS: dict = {"dense": True, "text_size": 13, "border_color": ft.Colors.GREY_300, "border_radius": 3}

    def __init__(self, page: ft.Page, config):
        self.page = page
        self.config = config
        self._file_path = config.paths.ssh_config_path
        self._ssh_dir = config.paths.ssh_dir
        self._keys_dir = os.path.join(self._ssh_dir, ".keys")
        self._mcp_dir = config.paths.mcp_dir
        self._data = self._load()
        self._mcp_servers = self._parse_mcp_table()
        self._build()

    @property
    def content_body(self) -> ft.Column:
        return self._content_body

    # ── MCP 表格解析 ──

    def _parse_mcp_table(self) -> list[dict]:
        """从 mcp.json 读取服务器列表，返回 [{'name': ..., 'desc': ...}, ...]"""
        mcp_json = self.config.mcp_config_path
        if not mcp_json or not os.path.isfile(mcp_json):
            return []

        try:
            with open(mcp_json, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            return []

        servers_config = config.get("servers", {})
        if not servers_config:
            return []

        return [
            {"name": name, "desc": cfg.get("desc", "")}
            for name, cfg in servers_config.items()
        ]

    # ── 密钥文件管理 ──

    def _list_key_files(self) -> list[str]:
        os.makedirs(self._keys_dir, exist_ok=True)
        files = []
        try:
            for f in os.listdir(self._keys_dir):
                if os.path.isfile(os.path.join(self._keys_dir, f)):
                    files.append(f)
        except FileNotFoundError:
            pass
        files.sort()
        return files

    async def _on_import_key(self, e):
        """zenity 选择文件 → 复制到 keys 目录"""
        proc = await asyncio.create_subprocess_exec(
            "zenity", "--file-selection", "--title=选择 SSH 密钥文件",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()
        if proc.returncode != 0:
            return
        src = stdout.decode("utf-8").strip()
        if not src or not os.path.isfile(src):
            return
        dst_name = os.path.basename(src)
        dst = os.path.join(self._keys_dir, dst_name)
        os.makedirs(self._keys_dir, exist_ok=True)
        shutil.copy2(src, dst)
        os.chmod(dst, 0o600)
        self._refresh_key_files_list()

    def _on_paste_key(self, e):
        """弹出粘贴密钥内容对话框"""
        tf_name = ft.TextField(
            label="文件名", hint_text="如 id_rsa",
            **self.TF_DEFAULTS, expand=True,
        )
        tf_content = ft.TextField(
            label="密钥内容", multiline=True, expand=True,
            min_lines=6, max_lines=14,
            text_size=11, border_color=ft.Colors.GREY_300,
        )
        def do_paste(e):
            name = (tf_name.value or "").strip()
            raw = (tf_content.value or "").strip()
            if not name or not raw:
                return
            os.makedirs(self._keys_dir, exist_ok=True)
            dst = os.path.join(self._keys_dir, name)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(raw)
            os.chmod(dst, 0o600)
            self._refresh_key_files_list()
            self.page.pop_dialog()

        dlg = ft.AlertDialog(
            shape=ft.RoundedRectangleBorder(radius=3),
            title=ft.Text("粘贴密钥内容", size=14),
            content=ft.Column([
                tf_name,
                ft.Container(tf_content, expand=True),
            ], spacing=10, width=440, expand=True, height=340),
            actions=[
                ft.TextButton(content="取消", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("保存", on_click=do_paste,
                                  style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=3))),
            ],
        )
        self.page.show_dialog(dlg)

    # ── 构建 UI ──

    def _build(self):
        # ── SSH管理区块 ──
        self._conn_col = ft.Column([], spacing=4)
        self._refresh_conn_list()

        self._key_files_col = ft.Column([], spacing=4)
        self._refresh_key_files_list()

        self._import_btn = ft.IconButton(
            icon=ft.Icons.FILE_OPEN,
            tooltip="导入密钥文件",
            icon_size=18,
            on_click=self._on_import_key,
        )
        self._paste_btn = ft.IconButton(
            icon=ft.Icons.CONTENT_PASTE,
            tooltip="粘贴密钥内容",
            icon_size=18,
            on_click=self._on_paste_key,
        )

        conn_section = ft.Column([
            ft.Divider(height=1, color=ft.Colors.GREY_300),
            ft.Text("📋 当前SSH", size=14, weight=ft.FontWeight.W_600),
            ft.Text("💡 添加/删除SSH请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
            self._conn_col,
            ft.Text("🔑 密钥文件", size=14, weight=ft.FontWeight.W_600),
            self._key_files_col,
            ft.Row([self._import_btn, self._paste_btn], spacing=4,
                   alignment=ft.MainAxisAlignment.END),
        ], spacing=8)

        # ── MCP 服务器区块 ──
        self._mcp_col = ft.Column([], spacing=4)
        self._refresh_mcp_list()

        mcp_section = ft.Column([
            ft.Divider(height=1, color=ft.Colors.GREY_300),
            ft.Text("🔌 MCP 可用服务器", size=14, weight=ft.FontWeight.W_600),
            ft.Text("💡 添加/删除 MCP 服务请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
            self._mcp_col,
        ], spacing=8)

        self._content_body = ft.Column([
            conn_section,
            mcp_section,
        ], expand=True, spacing=10)

    # ── SSH列表 ──

    def _build_conn_rows(self) -> list[ft.Row]:
        """构建连接行列表，仅展示信息，添加/删除通过 LLM 对话操作"""
        rows = []
        for c in self._data.get("connections", []):
            info_parts = [
                f"{c.get('username', '?')}@{c.get('host', '?')}:{c.get('port', 22)}",
            ]
            if c.get("auth_type") == "key":
                info_parts.append(f"🔑{c.get('key_path', '')}")
            else:
                info_parts.append("🔒密码")
            rows.append(ft.Row([
                ft.Column([
                    ft.Text(f"▸ {c.get('name', '?')}", size=12, weight=ft.FontWeight.W_500),
                    ft.Text(" | ".join(info_parts), size=11, color=ft.Colors.GREY_500),
                ], spacing=2, expand=True),
            ], spacing=4, alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
        return rows

    def _refresh_conn_list(self):
        rows = self._build_conn_rows()
        if rows:
            self._conn_col.controls = rows
        else:
            self._conn_col.controls = [
                ft.Text("  暂无连接配置", size=11, color=ft.Colors.GREY_400, italic=True)
            ]
        try:
            self._conn_col.update()
        except RuntimeError:
            pass
    # ── 密钥文件行 ──

    def _build_key_file_rows(self) -> list[ft.Row]:
        rows = []
        for f in self._list_key_files():
            del_btn = ft.IconButton(
                icon=ft.Icons.REMOVE,
                icon_size=16,
                icon_color=ft.Colors.RED_400,
                tooltip=f"删除 {f}",
                data=f,
                on_click=self._on_delete_key_click,
            )
            rows.append(ft.Row([
                ft.Text(f, size=12, expand=True),
                del_btn,
            ], spacing=4))
        return rows

    def _refresh_key_files_list(self):
        self._key_files_col.controls = self._build_key_file_rows()
        try:
            self._key_files_col.update()
        except RuntimeError:
            pass

    # ── MCP 服务器列表 ──

    def _build_mcp_rows(self) -> list:
        rows = []
        for s in self._mcp_servers:
            name = s["name"]
            desc = s["desc"]
            rows.append(ft.Column([
                ft.Text(f"▸ `{name}`", size=12, weight=ft.FontWeight.W_500),
                ft.Text(desc, size=11, color=ft.Colors.GREY_500),
            ], spacing=2))
        return rows

    def _refresh_mcp_list(self):
        rows = self._build_mcp_rows()
        if rows:
            self._mcp_col.controls = rows
        else:
            self._mcp_col.controls = [
                ft.Text("  暂无 MCP 服务器配置", size=11, color=ft.Colors.GREY_400, italic=True)
            ]
        try:
            self._mcp_col.update()
        except RuntimeError:
            pass

    # ── 删除操作 ──

    def _save(self):
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def _on_delete_key_click(self, e):
        filename = e.control.data
        dlg = ft.AlertDialog(
            shape=ft.RoundedRectangleBorder(radius=3),
            title=ft.Text("确认删除", size=14),
            content=ft.Text(f"确定删除密钥文件「{filename}」？此操作不可撤销。", size=13),
            actions=[
                ft.TextButton(content="取消", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("删除",
                                  style=ft.ButtonStyle(color=ft.Colors.RED_400, shape=ft.RoundedRectangleBorder(radius=3)),
                                  on_click=lambda e, fn=filename: self._do_delete_key(fn)),
            ],
        )
        self.page.show_dialog(dlg)

    def _do_delete_key(self, filename):
        path = os.path.join(self._keys_dir, filename)
        if os.path.isfile(path):
            os.remove(path)
        self.page.pop_dialog()
        self._refresh_key_files_list()

    # ── 数据 I/O ──

    def _load(self) -> dict:
        if os.path.exists(self._file_path):
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = {"key_path": "", "connections": []}
            if "key_path" in data:
                result["key_path"] = data["key_path"]
            if "connections" in data:
                result["connections"] = data["connections"]
                if not result["key_path"] and result["connections"]:
                    result["key_path"] = result["connections"][0].get("key_path", "")
                return result
            if "hosts" in data:
                # 迁移旧格式：hosts → connections
                migrated = []
                for h in data["hosts"]:
                    migrated.append({
                        "name": h.get("name", ""),
                        "host": h.get("ip", h.get("hostname", "")),
                        "port": h.get("port", 22),
                        "username": h.get("user", h.get("username", "")),
                        "auth_type": h.get("auth_type", "password"),
                        "password": h.get("password", ""),
                        "key_path": h.get("key_path", ""),
                    })
                result["connections"] = migrated
                if not result["key_path"]:
                    result["key_path"] = migrated[0].get("key_path", "") if migrated else ""
                return result
            return result
        return {"key_path": "", "connections": []}
