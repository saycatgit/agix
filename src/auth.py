"""权限规则系统

基于黑名单的危险命令检查。敏感命令命中即拦截。
交互模式弹窗确认，非交互模式直接拒绝。
"""

import re
from typing import Tuple, List

# ── 动作识别：命令 → 统一动作标识 ──
ACTION_PATTERNS = [
    (r'\brm\s+-[rRf]+\b', 'rm -rf'),
    (r'\brm\b(?!\s+-)', 'rm'),
    (r'\bsudo\b', 'sudo'),
    (r'\bchmod\b', 'chmod'),
    (r'\bchown\b', 'chown'),
    (r'\bmkfs\.', 'mkfs'),
    (r'\bdd\s+if=', 'dd'),
    (r'\bpasswd\b', 'passwd'),
    (r'\bkill\s+-9\b', 'kill -9'),
    (r'\bkill\b', 'kill'),
    (r'\bapt\s+(install|remove|purge)', 'apt'),
    (r'\bapt-get\b', 'apt-get'),
    (r'\byum\b', 'yum'),
    (r'\bdnf\b', 'dnf'),
    (r'\bpip\b', 'pip'),
    (r'\bnpm\b', 'npm'),
    (r'\biptables\b', 'iptables'),
    (r'\bwget\s+.*\|\s*(sh|bash)', 'wget | sh'),
    # Windows 危险命令
    (r'\bdel\s+/[fF]\b', 'del /f'),
    (r'\bformat\s+[a-zA-Z]:', 'format'),
    (r'\breg\s+(delete|add)\b', 'reg'),
    (r'\bdiskpart\b', 'diskpart'),
    (r'\bnet\s+(user|localgroup)\b', 'net user/group'),
    (r'\bshutdown\s+/[srf]', 'shutdown'),
    (r'\btakeown\b', 'takeown'),
    (r'\bicacls\b', 'icacls'),
    (r'\bbcdedit\b', 'bcdedit'),
    (r'\bwmic\b', 'wmic'),
    # PowerShell 危险命令
    (r'\bRemove-Item\b.*-[rR]ecurse.*-[fF]orce', 'Remove-Item -Recurse -Force'),
    (r'\bRemove-Item\b.*-[fF]orce.*-[rR]ecurse', 'Remove-Item -Recurse -Force'),
    (r'\bSet-ExecutionPolicy\b', 'Set-ExecutionPolicy'),
    (r'\bInvoke-Expression\b|\biex\s', 'Invoke-Expression'),
    (r'\bStop-Computer\b|\bRestart-Computer\b', 'Stop/Restart-Computer'),
    (r'\bStop-Process\b', 'Stop-Process'),
    (r'\bAdd-Type\b', 'Add-Type'),
    (r'\bClear-EventLog\b|\bwevtutil\s+cl\b', 'Clear-EventLog'),
    (r'\bSet-MpPreference\b|\bAdd-MpPreference\b', 'MpPreference'),
    (r'\bvssadmin\s+delete\s+shadows\b', 'vssadmin delete shadows'),
    (r'\bSet-ItemProperty\b.*\bHK(LM|CU|CR|U)\b', 'Set-ItemProperty Registry'),
    (r'\bNew-ItemProperty\b.*\bHK(LM|CU|CR|U)\b', 'Set-ItemProperty Registry'),
    (r'\bRemove-ItemProperty\b.*\bHK(LM|CU|CR|U)\b', 'Set-ItemProperty Registry'),
    (r'\bDisable-ComputerRestore\b', 'Disable-ComputerRestore'),
    (r'\bSet-Service\b|\bNew-Service\b|\bStop-Service\b', 'Set/New/Stop-Service'),
    (r'\bschtasks\s+/create\b', 'schtasks /create'),
    (r'\bSet-Acl\b', 'Set-Acl'),
    (r'\bUnblock-File\b', 'Unblock-File'),
    (r'\bpowershell\b|\bpwsh\b', 'powershell'),
    # macOS 危险命令
    (r'\bdiskutil\b', 'diskutil'),
    (r'\blaunchctl\s+(unload|remove)', 'launchctl'),
    (r'\bsoftwareupdate\b', 'softwareupdate'),
    (r'\bcsrutil\b', 'csrutil'),
    (r'\bnvram\b', 'nvram'),
    (r'\bcurl\s+.*\|\s*(sh|bash)', 'curl | sh'),
    (r'\bssh\b', 'ssh'),
    (r'\bscp\b', 'scp'),
    (r'\bmount\b', 'mount'),
    (r'\bnc\s+-[lL]\b', 'nc -l'),
    (r'\bcat\s+/etc/(shadow|passwd)', 'cat /etc/*'),
    (r'\bgit\s+reset\s+--hard\b', 'git reset --hard'),
    (r'\bgit\s+push\b.*--force', 'git push --force'),
    (r'>\s*/dev/sd[a-z]', '> /dev/sdX'),
]

# ── 敏感动作标记（哪些动作需要权限检查） ──
SENSITIVE_ACTIONS = {
    'rm -rf', 'rm', 'sudo', 'chmod', 'chown', 'mkfs', 'dd',
    'passwd', 'kill -9', 'kill', 'apt', 'apt-get', 'yum', 'dnf',
    'pip', 'npm', 'iptables', 'wget | sh', 'curl | sh', 'ssh',
    'scp', 'mount', 'nc -l', 'cat /etc/*',
    'git reset --hard', 'git push --force', '> /dev/sdX',
    # Windows
    'del /f', 'format', 'reg', 'diskpart', 'net user/group',
    'shutdown', 'takeown', 'icacls', 'bcdedit', 'wmic',
    # macOS
    # PowerShell
    'Remove-Item -Recurse -Force', 'Set-ExecutionPolicy', 'Invoke-Expression',
    'Stop/Restart-Computer', 'Stop-Process', 'Add-Type', 'Clear-EventLog',
    'MpPreference', 'vssadmin delete shadows', 'Set-ItemProperty Registry',
    'Disable-ComputerRestore', 'Set/New/Stop-Service', 'schtasks /create',
    'Set-Acl', 'Unblock-File', 'powershell',
    'diskutil', 'launchctl', 'softwareupdate', 'csrutil', 'nvram',
}

# ── 动作中文描述（供 check_dangerous 返回） ──
ACTION_DESCRIPTIONS = {
    'rm -rf': '递归强制删除', 'rm': '删除文件', 'sudo': '提权操作',
    'chmod': '修改文件权限', 'chown': '修改文件属主',
    'mkfs': '格式化文件系统', 'dd': '裸磁盘写入',
    'passwd': '修改密码', 'kill -9': '强制终止进程', 'kill': '终止进程',
    'apt': '系统包管理', 'apt-get': '系统包管理', 'yum': '系统包管理',
    'dnf': '系统包管理', 'pip': 'Python包管理', 'npm': 'Node包管理',
    'iptables': '防火墙配置', 'wget | sh': '远程脚本管道执行',
    'curl | sh': '远程脚本管道执行', 'ssh': 'SSH连接', 'scp': '文件传输',
    'mount': '挂载文件系统', 'nc -l': '网络监听',
    'cat /etc/*': '读取系统敏感文件',
    'git reset --hard': 'Git硬重置', 'git push --force': 'Git强制推送',
    '> /dev/sdX': '覆盖磁盘设备',
    # Windows
    'del /f': '强制删除文件', 'format': '格式化磁盘',
    'reg': '注册表操作', 'diskpart': '磁盘分区工具',
    'net user/group': '用户/组管理', 'shutdown': '关机/重启',
    'takeown': '获取文件所有权', 'icacls': '修改ACL权限',
    'bcdedit': '启动配置编辑', 'wmic': 'WMI管理操作',
    # macOS
    # PowerShell
    'Remove-Item -Recurse -Force': '递归强制删除(PS)', 'Set-ExecutionPolicy': '修改执行策略',
    'Invoke-Expression': '动态代码执行', 'Stop/Restart-Computer': '关机/重启',
    'Stop-Process': '终止进程', 'Add-Type': '加载.NET代码',
    'Clear-EventLog': '清除事件日志', 'MpPreference': 'Defender策略修改',
    'vssadmin delete shadows': '删除卷影副本', 'Set-ItemProperty Registry': '注册表写入',
    'Disable-ComputerRestore': '禁用系统还原', 'Set/New/Stop-Service': '服务管理',
    'schtasks /create': '创建计划任务', 'Set-Acl': '修改ACL权限',
    'Unblock-File': '移除文件安全标记', 'powershell': 'PowerShell执行',
    'diskutil': '磁盘工具操作', 'launchctl': '系统服务管理',
    'softwareupdate': '系统更新', 'csrutil': 'SIP完整性保护配置',
    'nvram': 'NVRAM固件变量',
}


class AuthHandler:
    """权限规则引擎

    职责:
        - 黑名单危险命令检查
        - 交互模式弹窗确认 / 非交互模式直接拒绝

    使用方式:
        ah = AuthHandler(interactive=True, sensitive_command_check=True)
        is_danger, descriptions = ah.check_dangerous(command)
    """

    def __init__(self, interactive: bool = True, sensitive_command_check: bool = True):
        self.interactive = interactive
        self.sensitive_command_check = sensitive_command_check
        # 会话级别允许/拒绝列表（内存维护，不落盘，程序重启后失效）
        self.session_allow_list: List[str] = []
        self.session_deny_list: List[str] = []

    def check_dangerous(self, command: str):
        """黑名单危险命令检查。

        返回 (is_dangerous: bool, descriptions: list[str])。
        受 sensitive_command_check 开关控制。
        """
        if not self.sensitive_command_check:
            return False, []
        action = self.extract_action(command)
        if action in SENSITIVE_ACTIONS:
            desc = ACTION_DESCRIPTIONS.get(action, action)
            return True, [desc]
        return False, []

    def check_session(self, command: str) -> str | None:
        """检查命令是否命中会话级别允许/拒绝列表。

        返回:
            "allow" — 命中允许列表，直接放行
            "deny"  — 命中拒绝列表，直接拦截
            None    — 未命中任何列表，需要弹窗确认

        匹配方式: 子串匹配（command 包含列表项即命中）。
        拒绝列表优先于允许列表（同时命中时拒绝）。
        """
        if not self.session_allow_list and not self.session_deny_list:
            return None
        for denied in self.session_deny_list:
            if denied in command:
                return "deny"
        for allowed in self.session_allow_list:
            if allowed in command:
                return "allow"
        return None

    def add_session_allow(self, command: str):
        """将命令加入会话允许列表"""
        self.session_allow_list.append(command)

    def add_session_deny(self, command: str):
        """将命令加入会话拒绝列表"""
        self.session_deny_list.append(command)

    @staticmethod
    def extract_action(command: str) -> str:
        """从命令文本提取动作标识

        通过预定义的正则模式 (ACTION_PATTERNS) 匹配命令中的敏感操作。
        """
        cmd = command.strip()
        for pattern, action in ACTION_PATTERNS:
            if re.search(pattern, cmd):
                return action
        return cmd.split()[0] if cmd.split() else cmd
