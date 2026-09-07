# -*- coding: utf-8 -*-
from __future__ import annotations
import base64
import binascii
import bisect
import hashlib
import json
import lzma
import random
import re
import struct
import threading
import time
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
import requests
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    hashes = None
    Cipher = algorithms = modes = None
try:
    from Crypto.Cipher import AES as CryptoAES
except ImportError:
    CryptoAES = None
from base.spider import Spider

# ====== AES 后端适配（不动）======
if Cipher is not None:
    AES_BACKEND = "cryptography"
elif CryptoAES is not None:
    AES_BACKEND = "pycryptodome"
else:
    AES_BACKEND = "none"

def _aes_ctr_decrypt(key: bytes, counter: bytes, data: bytes) -> bytes:
    if not data:
        return b""
    if AES_BACKEND == "cryptography":
        decryptor = Cipher(algorithms.AES(key), modes.CTR(counter)).decryptor()
        return decryptor.update(data) + decryptor.finalize()
    if AES_BACKEND == "pycryptodome":
        cipher = CryptoAES.new(
            key, CryptoAES.MODE_CTR, nonce=b"", initial_value=counter
        )
        return cipher.decrypt(data)
    raise HongguoPluginError("缺少 AES 实现：需要 cryptography 或 pycryptodome")

def _aes_cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if not data:
        return b""
    if AES_BACKEND == "cryptography":
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        return decryptor.update(data) + decryptor.finalize()
    if AES_BACKEND == "pycryptodome":
        return CryptoAES.new(key, CryptoAES.MODE_CBC, iv).decrypt(data)
    raise HongguoPluginError("缺少 AES 实现：需要 cryptography 或 pycryptodome")

# ====== 常量（不动）======
SITE = "https://hongguoduanju.com"
EPISODE_PREFIX = "hg-episode-v1:"
VIDEO_URL = "https://api5-normal-sinfonlineb.fqnovel.com/novel/player/multi_video_model/v1/"
API_HOST = "https://api5-normal-sinfonlineb.fqnovel.com"
UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
APP_UA = "com.phoenix.read/71332 (Linux; U; Android 16; zh_CN; 25053RT47C; Build/BP2A.250605.031.A3; Cronet/TTNetVersion:04657795 2026-01-23 QuicVersion:c67e9834 2025-09-08)"
MEDIA_UA = "com.phoenix.read/71332"

_HTML_FETCH_ATTEMPTS = 3
_HTML_FETCH_BACKOFF_SECONDS = 1.5
_RANGE_FETCH_ATTEMPTS = 3
_RANGE_FETCH_BACKOFF_SECONDS = 0.8

class HongguoPluginError(RuntimeError):
    pass

# ====== 工具函数（不动）======
def _text(value: Any) -> str:
    return str(value or "").strip()

def _first(*values: Any) -> str:
    for value in values:
        if isinstance(value, (list, tuple)):
            result = _first(*value)
        elif isinstance(value, Mapping):
            result = _first(
                value.get("url"),
                value.get("uri"),
                value.get("src"),
                value.get("download_url"),
                value.get("main_url"),
                value.get("backup_url"),
                value.get("backup_url_1"),
                value.get("play_addr"),
                value.get("url_list"),
            )
        else:
            result = _text(value)
        if result:
            return result
    return ""

def _json_response(response: requests.Response) -> Any:
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise HongguoPluginError("上游响应不是 JSON") from exc

def _get_html(url: str, *, attempts: int = _HTML_FETCH_ATTEMPTS) -> str:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
                timeout=30,
            )
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except Exception as error:
            last_error = error
            if attempt + 1 < max(1, attempts):
                time.sleep(_HTML_FETCH_BACKOFF_SECONDS * (attempt + 1))
    raise HongguoPluginError(f"fetch failed: {url}") from last_error

def _router_data(html: str) -> dict[str, Any]:
    match = re.search(r"(?:window\.)?_ROUTER_DATA\s*=\s*", html)
    if not match:
        raise HongguoPluginError("页面没有路由数据")
    try:
        value, _ = json.JSONDecoder().raw_decode(html[match.end():])
    except json.JSONDecodeError as exc:
        raise HongguoPluginError("页面路由数据解析失败") from exc
    if not isinstance(value, dict):
        raise HongguoPluginError("页面路由数据格式错误")
    return value

def _media_url(item: Mapping[str, Any]) -> str:
    return _first(
        item.get("main_url"),
        item.get("backup_url"),
        item.get("backup_url_1"),
        item.get("play_addr"),
        item.get("url"),
    )

def _spade_value(item: Mapping[str, Any]) -> str:
    encrypt_info = item.get("encrypt_info")
    if not isinstance(encrypt_info, Mapping):
        encrypt_info = {}
    return _first(item.get("spade_a"), encrypt_info.get("spade_a"))

# ====== 密钥派生（不动）======
def derive_content_key(spade_b64: str) -> bytes:
    raw = _b64(spade_b64)
    if len(raw) < 3:
        raise HongguoPluginError("spade_a 太短")
    v8 = len(raw) - (raw[0] ^ raw[1] ^ raw[2]) + 47
    if v8 <= 0 or 1 + v8 > len(raw):
        v8 = len(raw) - 1
    if v8 < 33:
        raise HongguoPluginError("spade_a 长度异常")
    value = bytearray(raw[1: 1 + v8])
    va, vb = 85, 246
    for index in range(v8):
        previous = va if index & 1 else vb
        if index & 1:
            va = value[index]
        else:
            vb = value[index]
        value[index] = (-21 - bin(index).count("1") + (previous ^ value[index])) & 0xFF
    try:
        return binascii.unhexlify(bytes(value[1:33]).decode("ascii"))
    except (ValueError, binascii.Error) as exc:
        raise HongguoPluginError("spade_a 密钥材料无效") from exc

# ====== MP4 / CENC 解析（不动）======
def _find_box(data: memoryview, fourcc: bytes, start: int) -> tuple[int, int]:
    for index in range(max(4, start), len(data) - 4):
        if data[index: index + 4] != fourcc:
            continue
        size = struct.unpack(">I", data[index - 4: index])[0]
        if size == 1 and index + 12 <= len(data):
            size = struct.unpack(">Q", data[index + 4: index + 12])[0]
        if 8 <= size <= 5_000_000 and index - 4 + size <= len(data):
            return index - 4, size
    return -1, 0

def _box_body(data: memoryview, fourcc: bytes, start: int) -> memoryview | None:
    offset, size = _find_box(data, fourcc, start)
    return data[offset + 8: offset + size] if offset >= 0 else None

def _parse_track(moov: memoryview, track_offset: int):
    if track_offset < 0:
        return None
    stbl_offset, _ = _find_box(moov, b"stbl", track_offset + 8)
    if stbl_offset < 0:
        return None
    stsz = _box_body(moov, b"stsz", stbl_offset)
    stco = _box_body(moov, b"stco", stbl_offset)
    co64 = _box_body(moov, b"co64", stbl_offset)
    stsc = _box_body(moov, b"stsc", stbl_offset)
    saiz = _box_body(moov, b"saiz", stbl_offset)
    saio = _box_body(moov, b"saio", stbl_offset)
    if any(v is None for v in (stsz, stsc, saiz, saio)) or (stco is None and co64 is None):
        return None
    default_size = struct.unpack(">I", stsz[4:8])[0]
    sample_count = struct.unpack(">I", stsz[8:12])[0]
    sizes = (
        [default_size] * sample_count
        if default_size
        else [
            struct.unpack(">I", stsz[12 + i * 4: 16 + i * 4])[0]
            for i in range(sample_count)
        ]
    )
    chunk_table = stco if stco is not None else co64
    chunk_count = struct.unpack(">I", chunk_table[4:8])[0]
    chunk_width = 4 if stco is not None else 8
    offsets = [
        int.from_bytes(chunk_table[8 + i * chunk_width: 8 + (i + 1) * chunk_width], "big")
        for i in range(chunk_count)
    ]
    entry_count = struct.unpack(">I", stsc[4:8])[0]
    entries = [
        (
            struct.unpack(">I", stsc[8 + i * 12: 12 + i * 12])[0],
            struct.unpack(">I", stsc[12 + i * 12: 16 + i * 12])[0],
        )
        for i in range(entry_count)
    ]
    chunk_samples = [0] * chunk_count
    for i, (first_chunk, samples_per_chunk) in enumerate(entries):
        end = entries[i + 1][0] - 1 if i + 1 < len(entries) else chunk_count
        for chunk in range(first_chunk - 1, min(end, chunk_count)):
            chunk_samples[chunk] = samples_per_chunk
    saiz_flags = int.from_bytes(saiz[1:4], "big")
    saiz_cursor = 12 if saiz_flags & 1 else 4
    if len(saiz) < saiz_cursor + 5:
        return None
    default_aux_size = saiz[saiz_cursor]
    aux_count = struct.unpack(">I", saiz[saiz_cursor + 1: saiz_cursor + 5])[0]
    aux_sizes = (
        [default_aux_size] * aux_count
        if default_aux_size
        else [
            int(saiz[saiz_cursor + 5 + i])
            for i in range(aux_count)
            if saiz_cursor + 5 + i < len(saiz)
        ]
    )
    saio_flags = int.from_bytes(saio[1:4], "big")
    saio_cursor = 12 if saio_flags & 1 else 4
    offset_width = 8 if saio[0] == 1 else 4
    if len(saio) < saio_cursor + 4 + offset_width:
        return None
    entry_count2 = int.from_bytes(saio[saio_cursor: saio_cursor + 4], "big")
    if entry_count2 < 1:
        return None
    aux_offset = int.from_bytes(
        saio[saio_cursor + 4: saio_cursor + 4 + offset_width], "big"
    )
    return sizes, offsets, chunk_samples, aux_sizes, aux_offset, sample_count

def _replace_fourcc(data: bytearray, old: bytes, new: bytes) -> None:
    position = 0
    while True:
        position = data.find(old, position)
        if position < 0:
            return
        data[position: position + len(old)] = new
        position += len(new)

def _replace_sinf(data: bytearray) -> None:
    position = 0
    while True:
        position = data.find(b"sinf", position)
        if position < 0:
            return
        if position >= 4:
            size = struct.unpack(">I", data[position - 4: position])[0]
            end = position - 4 + size
            if 8 <= size < 50_000 and end <= len(data):
                data[position: position + 4] = b"free"
                data[position + 4: end] = b"\x00" * max(0, end - position - 4)
                position = end
                continue
        position += 4

def decrypt_mp4_cenc(data: bytes, content_key: bytes) -> bytes:
    if len(content_key) != 16:
        raise HongguoPluginError("CENC 密钥长度错误")
    result = bytearray(data)
    if len(result) < 16:
        raise HongguoPluginError("MP4 数据过短")
    moov_start, moov_size = _find_box(memoryview(result), b"moov", 0)
    if moov_start < 0 or moov_size < 8:
        raise HongguoPluginError("MP4 moov 越界")
    moov = memoryview(result)[moov_start: moov_start + moov_size]
    tracks: list[int] = []
    track_search = 0
    while True:
        track, track_size = _find_box(moov, b"trak", track_search)
        if track < 0:
            break
        tracks.append(track)
        track_search = track + max(track_size, 8)
    decrypted_samples = 0
    for track in tracks:
        parsed = _parse_track(moov, track)
        if parsed is None:
            continue
        sizes, offsets, chunk_counts, aux_sizes, aux_offset, sample_count = parsed
        aux_size = sum(max(size, 8) for size in aux_sizes)
        if not sample_count or aux_offset < 0 or aux_offset + aux_size > len(result):
            continue
        aux = result[aux_offset: aux_offset + aux_size]
        sample_index = 0
        aux_index = 0
        for chunk_index, chunk_offset in enumerate(offsets):
            current = chunk_offset
            for _ in range(chunk_counts[chunk_index]):
                if sample_index >= sample_count or sample_index >= len(sizes):
                    break
                size = sizes[sample_index]
                if current + size > len(result):
                    raise HongguoPluginError("MP4 样本越界")
                if sample_index >= len(aux_sizes):
                    raise HongguoPluginError("MP4 辅助信息数量不足")
                entry_size = max(aux_sizes[sample_index], 8)
                iv = bytes(aux[aux_index: aux_index + min(entry_size, 8)]).ljust(8, b"\0") + b"\0" * 8
                result[current: current + size] = _aes_ctr_decrypt(
                    content_key, iv, bytes(result[current: current + size])
                )
                current += size
                sample_index += 1
                aux_index += entry_size
                decrypted_samples += 1
    if not decrypted_samples:
        raise HongguoPluginError("MP4 没有可解密的 CENC 样本")
    moov_buffer = bytearray(result[moov_start: moov_start + moov_size])
    _replace_fourcc(moov_buffer, b"encv", b"hvc1")
    _replace_fourcc(moov_buffer, b"enca", b"mp4a")
    _replace_sinf(moov_buffer)
    result[moov_start: moov_start + moov_size] = moov_buffer
    return bytes(result)

# ====== 流媒体服务（不动）======
MEDIA_HEADERS = {"User-Agent": MEDIA_UA, "Referer": "https://novel.snssdk.com/"}
_STREAM_PORT_RANGE = (9990, 10000)
_STREAM_CHUNK = 1 << 20
_STREAM_HEAD_PROBE = 1 << 16
_STREAM_TTL_SECONDS = 900
_STREAM_MAX_SESSIONS = 4
_STREAM_STATE: dict[str, Any] = {"port": 0, "server": None, "sessions": {}}
_STREAM_LOCK = threading.RLock()

def _toplevel_boxes(buf: bytes) -> list[tuple[int, int, bytes]]:
    boxes = []
    cursor = 0
    while cursor + 8 <= len(buf):
        size = struct.unpack(">I", buf[cursor: cursor + 4])[0]
        fourcc = bytes(buf[cursor + 4: cursor +
