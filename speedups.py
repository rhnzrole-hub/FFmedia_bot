"""
FF Media Bot - High-Performance Cryptography Speedups for Hydrogram.
Replaces slow pure-Python 'pyaes' with C-accelerated PyCryptodome AES-NI hardware engines.
Provides up to ~500x faster decryption and encryption for Telegram MTProto transfers.
"""

import logging
from Crypto.Cipher import AES
from Crypto.Util.strxor import strxor
import hydrogram.crypto.aes as haes

logger = logging.getLogger("FFMediaBot.Speedups")


def fast_ctr256(
    data: bytes, key: bytes, iv: bytearray, state: bytearray | None = None
) -> bytes:
    """Ultra-fast, hardware-accelerated CTR-256 using PyCryptodome AES-NI.

    Properly maintains and updates `iv` and `state` in-place so obfuscated TCP
    streams decrypt and encrypt seamlessly without timing out.
    """
    if not data:
        return b""
    if state is None:
        state = bytearray(1)

    data_len = len(data)
    out = []
    idx = 0
    st = state[0]

    # 1. Handle partial initial block
    if st > 0:
        take = min(data_len, 16 - st)
        cipher_ecb = AES.new(key, AES.MODE_ECB)
        chunk = cipher_ecb.encrypt(bytes(iv))
        part = bytes(data[idx : idx + take])
        out.append(strxor(part, chunk[st : st + take]))
        st += take
        idx += take
        if st >= 16:
            st = 0
            iv_int = (int.from_bytes(iv, "big") + 1) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
            iv[:] = iv_int.to_bytes(16, "big")
        state[0] = st
        if idx >= data_len:
            return b"".join(out)

    # 2. Handle full 16-byte blocks using PyCryptodome hardware CTR mode (~500+ MB/s)
    rem_len = data_len - idx
    full_blocks = rem_len // 16
    if full_blocks > 0:
        bytes_to_process = full_blocks * 16
        cipher_ctr = AES.new(key, AES.MODE_CTR, initial_value=bytes(iv), nonce=b"")
        c_chunk = cipher_ctr.encrypt(data[idx : idx + bytes_to_process])
        out.append(c_chunk)
        idx += bytes_to_process
        iv_int = (int.from_bytes(iv, "big") + full_blocks) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        iv[:] = iv_int.to_bytes(16, "big")

    # 3. Handle trailing partial block
    tail_len = data_len - idx
    if tail_len > 0:
        cipher_ecb = AES.new(key, AES.MODE_ECB)
        chunk = cipher_ecb.encrypt(bytes(iv))
        part = bytes(data[idx:])
        out.append(strxor(part, chunk[:tail_len]))
        state[0] = tail_len

    return b"".join(out)


def fast_ctr256_encrypt(
    data: bytes, key: bytes, iv: bytearray, state: bytearray | None = None
) -> bytes:
    return fast_ctr256(data, key, iv, state)


def fast_ctr256_decrypt(
    data: bytes, key: bytes, iv: bytearray, state: bytearray | None = None
) -> bytes:
    return fast_ctr256(data, key, iv, state)


def fast_ige256_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Ultra-fast IGE-256 decryption using PyCryptodome ECB + C-level strxor."""
    cipher = AES.new(key, AES.MODE_ECB)
    iv_1 = iv[:16]
    iv_2 = iv[16:]
    res = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        decrypted = cipher.decrypt(strxor(chunk, iv_2))
        plain = strxor(decrypted, iv_1)
        iv_1 = chunk
        iv_2 = plain
        res.append(plain)
    return b"".join(res)


def fast_ige256_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Ultra-fast IGE-256 encryption using PyCryptodome ECB + C-level strxor."""
    cipher = AES.new(key, AES.MODE_ECB)
    iv_1 = iv[:16]
    iv_2 = iv[16:]
    res = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        encrypted = cipher.encrypt(strxor(chunk, iv_1))
        cipher_chunk = strxor(encrypted, iv_2)
        iv_1 = cipher_chunk
        iv_2 = chunk
        res.append(cipher_chunk)
    return b"".join(res)


def apply_speedups():
    """Applies high-performance cryptography routines to Hydrogram's AES module.

    If tgcrypto (native C extension) is available, Hydrogram already uses it natively
    at 100+ MB/s. In that case, we keep TgCrypto.
    If tgcrypto is missing, we fall back to PyCryptodome to avoid pyaes slowness.
    """
    try:
        import tgcrypto
        # Verify tgcrypto has required methods
        if hasattr(tgcrypto, "ige256_decrypt") and hasattr(tgcrypto, "ctr256_decrypt"):
            logger.info("🚀 Native C TgCrypto detected! Full hardware encryption/decryption enabled (100+ MB/s).")
            return
    except ImportError:
        pass

    haes.ctr256_decrypt = fast_ctr256_decrypt
    haes.ctr256_encrypt = fast_ctr256_encrypt
    haes.ige256_decrypt = fast_ige256_decrypt
    haes.ige256_encrypt = fast_ige256_encrypt
    logger.info("⚡ PyCryptodome AES-NI fallback enabled (TgCrypto not found).")
