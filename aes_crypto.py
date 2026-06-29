"""AES 加密/解密工具：使用磁盘序列号作为密钥，保护 API Key 存储。

加密: AES-256-GCM（认证加密），密钥由磁盘序列号经 SHA-256 派生。
存储格式: enc:aes:<base64(nonce + ciphertext + tag)>
"""

import os,datetime
import hashlib
import base64
import subprocess
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ── 磁盘序列号获取 ─────────────────────────────────────────

def _get_disk_serial() -> str:
    """获取磁盘序列号，作为加密种子。

    优先级: lsblk → /sys/block/*/device/serial → /etc/machine-id → hostname
    返回: 稳定的机器唯一标识字符串。
    """
    # 1. lsblk（最可靠）
    try:
        result = subprocess.run(
            ['lsblk', '-o', 'SERIAL', '-n', '-d'],
            capture_output=True, text=True, timeout=5
        )
        lines = [l.strip() for l in result.stdout.split('\n') if l.strip()]
        if lines:
            return lines[0]
    except Exception:
        pass

    # 2. /sys 文件系统
    for dev in ['sda', 'vda', 'nvme0n1', 'hda', 'xvda']:
        path = f'/sys/block/{dev}/device/serial'
        try:
            with open(path) as f:
                serial = f.read().strip()
                if serial:
                    return serial
        except Exception:
            continue

    # 3. /etc/machine-id（容器/VM 通用）
    try:
        with open('/etc/machine-id') as f:
            return f.read().strip()
    except Exception:
        pass

    # 4. 最终兜底
    import socket
    return socket.gethostname()


# ── 密钥派生 ───────────────────────────────────────────────

def _derive_key(seed: str) -> bytes:
    """从任意长度种子（磁盘序列号）派生 256-bit AES 密钥。"""
    return hashlib.sha256(seed.encode('utf-8')).digest()


# ── 加密/解密 ───────────────────────────────────────────────

def encrypt(plaintext: str) -> str:
    """加密明文，返回 'enc:aes:<base64>' 格式的密文。

    Args:
        plaintext: 要加密的明文（API Key）

    Returns:
        'enc:aes:' 前缀 + base64 编码的密文数据（nonce + ciphertext）
    """
    seed = _get_disk_serial()
    key = _derive_key(seed)
    nonce = secrets.token_bytes(12)  # AES-GCM 推荐 12 字节 nonce

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

    # 打包: nonce + ciphertext → base64
    combined = nonce + ciphertext
    b64 = base64.urlsafe_b64encode(combined).decode('ascii')
    return f"enc:aes:{b64}"


def decrypt(encoded: str) -> str:
    """解密 'enc:aes:<base64>' 格式的密文，返回原始明文。

    Args:
        encoded: encrypt() 返回的密文字符串

    Returns:
        解密后的明文

    Raises:
        ValueError: 格式错误或解密失败（磁盘更换/篡改）
    """
    if not encoded.startswith('enc:aes:'):
        raise ValueError(f"Invalid format: expected 'enc:aes:' prefix, got: {encoded[:20]}...")

    b64 = encoded[8:]  # 去掉 'enc:aes:' 前缀
    combined = base64.urlsafe_b64decode(b64)

    nonce = combined[:12]
    ciphertext = combined[12:]

    seed = _get_disk_serial()
    key = _derive_key(seed)

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        raise ValueError(
            f"解密失败: {e}。可能原因: 磁盘序列号变化、配置文件被篡改、"
            f"或配置文件从其他机器复制而来。请重新运行配置向导。"
        )


# ── 便捷方法 ───────────────────────────────────────────────

def is_encrypted(value: str) -> bool:
    """判断字符串是否为加密格式。"""
    return value.startswith('enc:aes:')


# ── 自检 ───────────────────────────────────────────────────

if __name__ == '__main__':
    seed = _get_disk_serial()
    print(f"磁盘序列号(种子): {seed}")
    print(f"派生密钥(SHA-256): {_derive_key(seed).hex()}")

    test_key = "sk-test1234567890abcdef"
    enc = encrypt(test_key)
    print(f"加密: {enc[:60]}...")
    dec = decrypt(enc)
    print(f"解密: {dec}")
    assert dec == test_key, "加解密不匹配!"
    print("✅ 自检通过")
    print(datetime.datetime.now())
