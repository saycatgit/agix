"""通用工具类：系统提示音、加解密等"""

import os, glob, platform
import subprocess


class Utils:
    """通用工具方法集。"""

    @staticmethod
    def play_notification():
        """播放系统提示音（跨平台）。"""
        try:
            system = platform.system()
            if system == 'Windows':
                import winsound
                winsound.MessageBeep()
            elif system == 'Darwin':
                subprocess.run(['afplay', '/System/Library/Sounds/Ping.aiff'],
                               capture_output=True, timeout=2)
            else:
                # Linux: 多播放器降级
                sound_file = '/usr/share/sounds/freedesktop/stereo/complete.oga'
                for player in (['paplay', sound_file],
                               ['pw-play', sound_file],
                               ['aplay', '/usr/share/sounds/alsa/Front_Center.wav']):
                    try:
                        subprocess.run(player, capture_output=True, timeout=2, check=True)
                        return
                    except Exception:
                        continue
                raise RuntimeError('no player available')
        except Exception:
            print('\a', end='', flush=True)

    @staticmethod
    def encrypt(plaintext: str) -> str:
        """AES-256-GCM 加密，返回 'enc:aes:<base64>' 格式密文。"""
        from aes_crypto import encrypt as _encrypt
        return _encrypt(plaintext)

    @staticmethod
    def decrypt(encoded: str) -> str:
        """解密 'enc:aes:<base64>' 格式密文，返回明文。"""
        from aes_crypto import decrypt as _decrypt
        return _decrypt(encoded)

    @staticmethod
    def is_encrypted(value: str) -> bool:
        """判断字符串是否为加密格式。"""
        from aes_crypto import is_encrypted as _is_encrypted
        return _is_encrypted(value)

    @staticmethod
    def scan_skills_dir(skills_dir: str) -> str:
        """扫描 skills_dir 构建技能列表文本"""
        if not skills_dir or not os.path.isdir(skills_dir):
            return ""

        lines = ["## 可用技能（优先查看是否有可用技能）："]
        for skill_dir in sorted(glob.glob(os.path.join(skills_dir, "*"))):
            if not os.path.isdir(skill_dir):
                continue
            name = os.path.basename(skill_dir)
            md = os.path.join(skill_dir, "SKILL.md")
            desc = ""
            if os.path.isfile(md):
                try:
                    with open(md, "r", encoding="utf-8") as f:
                        first = f.readline().strip().lstrip("#").strip()
                        if first:
                            desc = first
                except Exception:
                    pass
            lines.append(f"- **{name}**: {desc or name}")
            lines.append(f"  文档: {md}")
        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def build_pretask_skills(skills_dir: str) -> str:
        """构建可用技能列表文本"""
        return Utils.scan_skills_dir(skills_dir)


if __name__ == "__main__":

    Utils.play_notification()
