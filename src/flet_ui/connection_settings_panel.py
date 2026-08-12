"""连接管理面板 UI 组件 —— 左侧分类导航(SSH/MCP/Skill/Keys) + 右侧详情区"""

import asyncio, glob, os, shutil, subprocess
import flet as ft


class ConnectionSettingsPanel:
    """连接管理面板：SSH / MCP / Skill / Keys 四分类展示"""

    PANEL_BGCOLOR = ft.Colors.WHITE
    LABEL_COLOR = ft.Colors.GREY_700
    TITLE_TEXT: str = "🔗 连接管理"
    NAV_WIDTH: int = 90

    CATEGORIES = [
        ("SSH", ft.Icons.TERMINAL),
        ("MCP", ft.Icons.HUB),
        ("Skill", ft.Icons.AUTO_AWESOME),
        ("Keys", ft.Icons.KEY),
    ]

    TF_DEFAULTS: dict = {"dense": True, "text_size": 13, "border_color": ft.Colors.GREY_300, "border_radius": 3}

    def __init__(self, page: ft.Page, agent):
        self.page = page
        self.agent = agent
        self.config = agent.config
        self._ssh_dir = agent.config.paths.ssh_dir
        self._keys_dir = os.path.join(self._ssh_dir, ".keys")
        self._skills_dir = agent.config.paths.skills_dir
        self._mcp_dir = agent.config.paths.mcp_dir
        self._active_cat = "SSH"
        self._build()

    @property
    def content_body(self) -> ft.Column:
        return self._content_body

    # ── 数据加载 ──

    def _load_ssh_list(self) -> list[dict]:
        """从 ssh.md 解析 '## 当前SSH' 下的 markdown 表格"""
        ssh_md = os.path.join(self._ssh_dir, "ssh.md")
        if not os.path.isfile(ssh_md):
            return []
        try:
            with open(ssh_md, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return []

        marker = "## 当前SSH"
        idx = content.find(marker)
        if idx == -1:
            return []

        section = content[idx + len(marker):]
        rows = []
        for line in section.strip().splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip().strip("`") for c in line.split("|")[1:-1]]
            if len(cells) < 5:
                continue
            if cells[0] in ("名称", "------", "---") or set(cells[0]) <= {"-"}:
                continue
            rows.append({
                "name": cells[0],
                "host": cells[1],
                "port": cells[2],
                "username": cells[3],
                "auth_type": cells[4],
            })
        return rows

    def _load_mcp_list(self) -> list[dict]:
        """从 mcp.md 解析 '## MCP可用服务器' 下的 markdown 表格"""
        mcp_md = os.path.join(self._mcp_dir, "mcp.md")
        if not os.path.isfile(mcp_md):
            return []
        try:
            with open(mcp_md, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return []

        marker = "## MCP可用服务器"
        idx = content.find(marker)
        if idx == -1:
            return []

        section = content[idx + len(marker):]
        rows = []
        for line in section.strip().splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip().strip("`") for c in line.split("|")[1:-1]]
            if len(cells) < 2:
                continue
            if cells[0] in ("服务器", "------", "---") or set(cells[0]) <= {"-"}:
                continue
            rows.append({"name": cells[0], "desc": cells[1]})
        return rows

    def _load_skill_list(self) -> list[dict]:
        """扫描 skills_dir，提取名称和描述"""
        if not self._skills_dir or not os.path.isdir(self._skills_dir):
            return []
        skills = []
        for skill_dir in sorted(glob.glob(os.path.join(self._skills_dir, "*"))):
            if not os.path.isdir(skill_dir):
                continue
            name = os.path.basename(skill_dir)
            desc = ""
            md = os.path.join(skill_dir, "SKILL.md")
            if os.path.isfile(md):
                try:
                    with open(md, "r", encoding="utf-8") as f:
                        f.readline()
                        for line in f:
                            stripped = line.strip()
                            if stripped:
                                desc = stripped
                                break
                except Exception:
                    pass
            skills.append({"name": name, "desc": desc or name})
        return skills

    # ── 构建 UI ──

    def _build(self):
        self._nav_btns = []
        for name, icon in self.CATEGORIES:
            btn = ft.Container(
                content=ft.Column([
                    ft.Icon(icon, size=20),
                    ft.Text(name, size=11),
                ], spacing=2, alignment=ft.MainAxisAlignment.CENTER,
                   horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(4, 10, 4, 10),
                border_radius=6,
                data=name,
                on_click=lambda e, n=name: self._switch_category(n),
                ink=True,
            )
            self._nav_btns.append(btn)

        nav_col = ft.Column(self._nav_btns, spacing=4, alignment=ft.MainAxisAlignment.START)
        self._detail_area = ft.Container(expand=True, padding=ft.Padding(12, 8, 8, 8))

        self._key_files_col = ft.Column([], spacing=4)
        self._import_btn = ft.IconButton(
            icon=ft.Icons.FILE_OPEN, tooltip="导入密钥文件", icon_size=18,
            on_click=self._on_import_key,
        )
        self._paste_btn = ft.IconButton(
            icon=ft.Icons.CONTENT_PASTE, tooltip="粘贴密钥内容", icon_size=18,
            on_click=self._on_paste_key,
        )

        self._content_body = ft.Column([
            ft.Row([
                ft.Container(content=nav_col, width=self.NAV_WIDTH,
                             bgcolor=ft.Colors.GREY_50, border_radius=6,
                             padding=ft.Padding(4, 8, 4, 8)),
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                self._detail_area,
            ], spacing=0, expand=True),
        ], expand=True, spacing=0)

        self._switch_category("SSH")

    def _switch_category(self, name: str):
        self._active_cat = name
        for btn in self._nav_btns:
            is_active = btn.data == name
            btn.bgcolor = ft.Colors.BLUE_50 if is_active else None
            col = btn.content
            if isinstance(col, ft.Column):
                for ctrl in col.controls:
                    if isinstance(ctrl, ft.Icon):
                        ctrl.color = ft.Colors.BLUE if is_active else ft.Colors.GREY_600
                    elif isinstance(ctrl, ft.Text):
                        ctrl.color = ft.Colors.BLUE if is_active else ft.Colors.GREY_700

        if name == "SSH":
            self._detail_area.content = self._build_ssh_detail()
        elif name == "MCP":
            self._detail_area.content = self._build_mcp_detail()
        elif name == "Skill":
            self._detail_area.content = self._build_skill_detail()
        elif name == "Keys":
            self._detail_area.content = self._build_keys_detail()

        try:
            self.page.update()
        except RuntimeError:
            pass

    # ── SSH 详情 ──

    def _build_ssh_detail(self) -> ft.Column:
        conns = self._load_ssh_list()
        if not conns:
            return ft.Column([
                ft.Text("SSH 连接", size=14, weight=ft.FontWeight.W_600),
                ft.Text("暂无连接配置", size=12, color=ft.Colors.GREY_400, italic=True),
                ft.Text("💡 添加/删除 SSH 请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
            ], spacing=8)

        rows = []
        for c in conns:
            auth_label = "🔑 密钥" if c["auth_type"] == "key" else "🔒 密码"
            rows.append(ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(c["name"], size=12, weight=ft.FontWeight.W_500),
                        ft.Text(f"{c['username']}@{c['host']}:{c['port']}", size=11, color=ft.Colors.GREY_500),
                    ], spacing=2, expand=True),
                    ft.Text(auth_label, size=11, color=ft.Colors.GREY_600),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding(8, 6, 8, 6),
                bgcolor=ft.Colors.GREY_50, border_radius=4,
            ))

        return ft.Column([
            ft.Text("SSH 连接", size=14, weight=ft.FontWeight.W_600),
            ft.Text(f"共 {len(conns)} 个连接", size=11, color=ft.Colors.GREY_500),
            ft.Column(rows, spacing=4),
            ft.Text("💡 添加/删除 SSH 请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
        ], spacing=8)

    # ── MCP 详情 ──

    def _build_mcp_detail(self) -> ft.Column:
        servers = self._load_mcp_list()
        if not servers:
            return ft.Column([
                ft.Text("MCP 服务器", size=14, weight=ft.FontWeight.W_600),
                ft.Text("暂无 MCP 服务器配置", size=12, color=ft.Colors.GREY_400, italic=True),
                ft.Text("💡 添加/删除 MCP 服务请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
            ], spacing=8)

        rows = []
        for s in servers:
            rows.append(ft.Container(
                content=ft.Column([
                    ft.Text(s["name"], size=12, weight=ft.FontWeight.W_500),
                    ft.Text(s["desc"], size=11, color=ft.Colors.GREY_500),
                ], spacing=2),
                padding=ft.Padding(8, 6, 8, 6),
                bgcolor=ft.Colors.GREY_50, border_radius=4,
            ))

        return ft.Column([
            ft.Text("MCP 服务器", size=14, weight=ft.FontWeight.W_600),
            ft.Text(f"共 {len(servers)} 个服务", size=11, color=ft.Colors.GREY_500),
            ft.Column(rows, spacing=4),
            ft.Text("💡 添加/删除 MCP 服务请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
        ], spacing=8)

    # ── Skill 详情 ──

    def _build_skill_detail(self) -> ft.Column:
        skills = self._load_skill_list()
        if not skills:
            return ft.Column([
                ft.Text("可用技能", size=14, weight=ft.FontWeight.W_600),
                ft.Text("暂无技能", size=12, color=ft.Colors.GREY_400, italic=True),
                ft.Text("💡 添加/删除技能请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
            ], spacing=8)

        rows = []
        for s in skills:
            rows.append(ft.Container(
                content=ft.Column([
                    ft.Text(s["name"], size=12, weight=ft.FontWeight.W_500),
                    ft.Text(s["desc"], size=11, color=ft.Colors.GREY_500),
                ], spacing=2),
                padding=ft.Padding(8, 6, 8, 6),
                bgcolor=ft.Colors.GREY_50, border_radius=4,
            ))

        return ft.Column([
            ft.Text("可用技能", size=14, weight=ft.FontWeight.W_600),
            ft.Text(f"共 {len(skills)} 个技能", size=11, color=ft.Colors.GREY_500),
            ft.Column(rows, spacing=4),
            ft.Text("💡 添加/删除技能请通过对话操作", size=11, color=ft.Colors.INDIGO_400),
        ], spacing=8)

    # ── Keys 详情 ──

    def _build_keys_detail(self) -> ft.Column:
        self._refresh_key_files_list()
        return ft.Column([
            ft.Text("密钥文件", size=14, weight=ft.FontWeight.W_600),
            self._key_files_col,
            ft.Row([self._import_btn, self._paste_btn], spacing=4,
                   alignment=ft.MainAxisAlignment.END),
        ], spacing=8)

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

    def _build_key_file_rows(self) -> list[ft.Row]:
        rows = []
        for f in self._list_key_files():
            del_btn = ft.IconButton(
                icon=ft.Icons.REMOVE, icon_size=16,
                icon_color=ft.Colors.RED_400, tooltip=f"删除 {f}",
                data=f, on_click=self._on_delete_key_click,
            )
            rows.append(ft.Row([
                ft.Text(f, size=12, expand=True),
                del_btn,
            ], spacing=4))
        return rows

    def _refresh_key_files_list(self):
        rows = self._build_key_file_rows()
        if rows:
            self._key_files_col.controls = rows
        else:
            self._key_files_col.controls = [
                ft.Text("  暂无密钥文件", size=11, color=ft.Colors.GREY_400, italic=True)
            ]
        try:
            self._key_files_col.update()
        except RuntimeError:
            pass

    async def _on_import_key(self, e):
        """文件选择 → 复制到 keys 目录"""
        if self.config.system == "windows":
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$o=New-Object System.Windows.Forms.Form; "
                "$o.TopMost=$true; $o.ShowInTaskbar=$false; "
                "$o.WindowState='Minimized'; $o.Show(); "
                "$d=New-Object System.Windows.Forms.OpenFileDialog; "
                "$d.Title='选择 SSH 密钥文件'; "
                "$d.Filter='所有文件 (*.*)|*.*'; "
                "$r=($d.ShowDialog($o) -eq 'OK'); "
                "$o.Close(); "
                "if($r){$d.FileName}"
            )
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-Command", ps_script,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        elif self.config.system == "darwin":
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", 'POSIX path of (choose file with prompt "选择 SSH 密钥文件")',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        else:
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
            bgcolor=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("粘贴密钥内容", size=14),
            content=ft.Column([
                tf_name,
                ft.Container(tf_content, expand=True),
            ], spacing=10, width=440, expand=True, height=340),
            actions=[
                ft.TextButton(content="取消", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("保存", on_click=do_paste,
                                  style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6))),
            ],
        )
        self.page.show_dialog(dlg)

    def _on_delete_key_click(self, e):
        filename = e.control.data
        dlg = ft.AlertDialog(
            bgcolor=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("确认删除", size=14),
            content=ft.Text(f"确定删除密钥文件「{filename}」？此操作不可撤销。", size=13),
            actions=[
                ft.TextButton(content="取消", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("删除",
                                  style=ft.ButtonStyle(color=ft.Colors.RED_400, shape=ft.RoundedRectangleBorder(radius=6)),
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
