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
