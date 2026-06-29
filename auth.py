"""权限规则系统

基于 动作(action) + 目标(target) 的三级规则表匹配。
规则持久化于 .agent_permissions.json。

规则模型:
    {"action": "rm -rf", "target": "*", "policy": "always_deny"}

匹配顺序 (首个命中即停止):
    1. always_deny  → 直接拒绝
    2. always_ask   → 弹窗确认
    3. always_allow → 直接放行
    4. 无匹配       → 弹窗确认

交互确认选项:
    [A] 总是允许  [D] 总是拒绝  [Y] 允许本次  [N] 拒绝本次
"""

import json
import re
from pathlib import Path
from typing import Optional, Tuple, List

RULES_PATH = Path(__file__).parent / ".agent_permissions.json"

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
]

# ── 敏感动作标记（哪些动作需要权限检查） ──
SENSITIVE_ACTIONS = {
    'rm -rf', 'rm', 'sudo', 'chmod', 'chown', 'mkfs', 'dd',
    'passwd', 'kill -9', 'kill', 'apt', 'apt-get', 'yum', 'dnf',
    'pip', 'npm', 'iptables', 'wget | sh', 'curl | sh', 'ssh',
    'scp', 'mount', 'nc -l', 'cat /etc/*',
}


class AuthHandler:
    """权限规则引擎

    职责:
        - 从命令文本中提取动作和目标
        - 查询规则表进行三级匹配
        - 无匹配时触发交互式确认

    使用方式:
        ah = AuthHandler(interactive=True)
        decision = ah.query(command)  # pass/deny/ask/allow/prompt
    """

    def __init__(self, interactive: bool = True, sensitive_command_check: bool = True):
        self.interactive = interactive
        self.sensitive_command_check = sensitive_command_check
        self._rules = self._load()

    # ── 持久化 ──

    @staticmethod
    def _load() -> List[dict]:
        if RULES_PATH.exists():
            try:
                return json.loads(RULES_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save(self):
        RULES_PATH.write_text(
            json.dumps(self._rules, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _log(self, msg: str, always: bool = True):
        if getattr(self, "logger", None):
            self.logger.log(msg, always=always)

    def add_rule(self, action: str, target: str, policy: str):
        """添加/覆盖规则

        同一 (action, target) 组合的旧规则会被替换。
        规则自动持久化到 .agent_permissions.json。
        """
        self._rules = [r for r in self._rules
                       if not (r["action"] == action and r["target"] == target)]
        self._rules.append({"action": action, "target": target, "policy": policy})
        self._save()

    # ── 命令解析 ──

    @staticmethod
    def extract_action(command: str) -> str:
        """从命令文本提取动作标识

        通过预定义的正则模式 (ACTION_PATTERNS) 匹配命令中的敏感操作，
        如 rm -rf、chmod、pip install 等。
        """
        cmd = command.strip()
        for pattern, action in ACTION_PATTERNS:
            if re.search(pattern, cmd):
                return action
        return cmd.split()[0] if cmd.split() else cmd

    @staticmethod
    def extract_targets(command: str) -> List[str]:
        """提取命令操作的目标路径

        匹配绝对路径、相对路径，无路径时取最后一个参数。
        """
        cmd = command.strip()
        targets = []
        # 绝对路径
        for m in re.finditer(r'(/[^\s;|&><]+)', cmd):
            targets.append(m.group(1))
        # 相对路径
        for m in re.finditer(r'(?<!\S)(\.{1,2}/[^\s;|&><]+)', cmd):
            targets.append(m.group(1))
        # 无路径时用最后一个参数
        if not targets:
            parts = cmd.split()
            if len(parts) > 1:
                targets.append(parts[-1])
        return targets

    # ── 规则匹配 ──

    @staticmethod
    def _target_match(rule_target: str, cmd_target: str) -> bool:
        """目标匹配：* 通配 / 前缀匹配 / 精确匹配"""
        if rule_target == '*':
            return True
        if cmd_target == rule_target:
            return True
        if cmd_target.startswith(rule_target.rstrip('/') + '/'):
            return True
        return False

    def _match(self, action: str, target: str, policy: str) -> bool:
        """查找是否有匹配的规则"""
        for rule in self._rules:
            if rule.get("policy") != policy:
                continue
            if rule.get("action") != action:
                continue
            if self._target_match(rule.get("target", "*"), target):
                return True
        return False

    # ── 权限查询（三级匹配） ──

    def query(self, command: str) -> str:
        """查询命令权限状态

        Args:
            command: 待检查的命令字符串

        Returns:
            权限决策:
            - pass:   非敏感命令，直接放行
            - deny:   命中 always_deny 规则
            - ask:    命中 always_ask 规则
            - allow:  命中 always_allow 规则
            - prompt: 敏感命令无匹配规则，需交互确认
        """
        # 敏感命令检查关闭时，全部放行
        if not self.sensitive_command_check:
            return 'pass'

        action = self.extract_action(command)
        if action not in SENSITIVE_ACTIONS:
            return 'pass'

        targets = self.extract_targets(command)
        if not targets:
            return 'pass'

        # 取最严格的匹配结果（有任一目标匹配 deny 则 deny）
        ask_found = False
        for target in targets:
            if self._match(action, target, 'always_deny'):
                return 'deny'
            if self._match(action, target, 'always_ask'):
                ask_found = True
        if ask_found:
            return 'ask'

        for target in targets:
            if self._match(action, target, 'always_allow'):
                return 'allow'

        return 'prompt'

    # ── 交互确认 ──

    def prompt(self, action: str, targets: List[str], command: str) -> str:
        """弹出交互式确认对话框

        Args:
            action: 提取的动作标识
            targets: 操作目标路径列表
            command: 完整命令原文

        Returns:
            用户选择: always_allow / always_deny / allow / deny
        """
        if not self.interactive:
            return 'deny'

        self._log("")
        self._log(f"\033[93m⚠ 权限确认\033[0m")
        self._log(f"   动作: {action}")
        self._log(f"   目标: {', '.join(targets[:5])}")
        self._log(f"   命令: {command[:120]}")
        self._log(f"   [A] 总是允许  [D] 总是拒绝  [Y] 允许  [N] 拒绝")

        try:
            choice = input("   请选择 [A/d/y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self._log('')
            return 'deny'

        mapping = {
            'a': 'always_allow', 'd': 'always_deny',
            'y': 'allow', 'n': 'deny',
        }
        result = mapping.get(choice, 'deny')
        labels = {
            'always_allow': "✓ 总是允许（已缓存）",
            'always_deny':  "✗ 总是拒绝（已缓存）",
            'allow':        "✓ 本次允许",
            'deny':         "✗ 本次拒绝",
        }
        msg = f"   {labels[result]}"
        self._log(msg)
        return result
