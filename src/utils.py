"""通用工具类：系统提示音、加解密等"""

import os, platform
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

if __name__ == "__main__":

    Utils.play_notification()
