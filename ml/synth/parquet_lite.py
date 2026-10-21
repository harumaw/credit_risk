"""Минимальный читатель Parquet на чистом Python + numpy — запасной вариант, когда нет pyarrow.

Поддерживает ровно то, что нужно для файлов соревнования scoring_maps: плоская схема,
INT32/INT64/FLOAT/DOUBLE, кодировки PLAIN и RLE_DICTIONARY, сжатие SNAPPY/GZIP/без сжатия,
страницы данных v1 и v2. Для остального используйте pandas + pyarrow.
"""

import struct
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

_NP_TYPES = {1: "<i4", 2: "<i8", 4: "<f4", 5: "<f8"}


class _Thrift:
    """Декодер thrift compact protocol (метаданные Parquet)."""

    def __init__(self, buf: bytes, pos: int = 0):
        self.b, self.p = buf, pos

    def varint(self) -> int:
        result = shift = 0
        while True:
            byte = self.b[self.p]
            self.p += 1
            result |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return result

    def zigzag(self) -> int:
        v = self.varint()
        return (v >> 1) ^ -(v & 1)

    def value(self, t: int):
        if t in (1, 2):
            return t == 1
        if t == 3:
            v = self.b[self.p]
            self.p += 1
            return v - 256 if v > 127 else v
        if t in (4, 5, 6):
            return self.zigzag()
        if t == 7:
            v = struct.unpack("<d", self.b[self.p : self.p + 8])[0]
            self.p += 8
            return v
        if t == 8:
            n = self.varint()
            v = self.b[self.p : self.p + n]
            self.p += n
            return v
        if t in (9, 10):
            head = self.b[self.p]
            self.p += 1
            n, elem = head >> 4, head & 15
            if n == 15:
                n = self.varint()
            if elem in (1, 2):
                out = [self.b[self.p + i] == 1 for i in range(n)]
                self.p += n
                return out
            return [self.value(elem) for _ in range(n)]
        if t == 12:
            return self.struct()
        raise ValueError(f"thrift type {t}")

    def struct(self) -> dict:
        fields, last = {}, 0
        while True:
            head = self.b[self.p]
            self.p += 1
            if head == 0:
                return fields
            delta = head >> 4
            fid = last + delta if delta else self.zigzag()
            last = fid
            fields[fid] = self.value(head & 15)


def _snappy(src: bytes) -> bytes:
    p = n = shift = 0
    while True:
        byte = src[p]
        p += 1
        n |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            break
    out = bytearray()
    while p < len(src):
        tag = src[p]
        p += 1
        kind = tag & 3
        if kind == 0:  # literal
            ln = tag >> 2
            if ln >= 60:
                nb = ln - 59
                ln = int.from_bytes(src[p : p + nb], "little")
                p += nb
            ln += 1
            out += src[p : p + ln]
            p += ln
            continue
        if kind == 1:
            ln = ((tag >> 2) & 7) + 4
            off = ((tag >> 5) << 8) | src[p]
            p += 1
        elif kind == 2:
            ln = (tag >> 2) + 1
            off = src[p] | (src[p + 1] << 8)
            p += 2
        else:
            ln = (tag >> 2) + 1
            off = int.from_bytes(src[p : p + 4], "little")
            p += 4
        start = len(out) - off
        if off >= ln:
            out += out[start : start + ln]
        else:  # перекрывающееся копирование
            for i in range(ln):
                out.append(out[start + i])
    if len(out) != n:
        raise ValueError("snappy: неверная длина")
    return bytes(out)


def _rle_bitpacked(buf: bytes, bit_width: int, count: int) -> np.ndarray:
    res = np.empty(count, dtype=np.int64)
    i = p = 0
    width_bytes = (bit_width + 7) // 8
    while i < count and p < len(buf):
        header = shift = 0
        while True:
            byte = buf[p]
            p += 1
            header |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        if header & 1:  # bit-packed группы по 8 значений
            groups = header >> 1
            nbytes = groups * bit_width
            if bit_width:
                chunk = np.frombuffer(buf[p : p + nbytes], dtype=np.uint8)
                bits = np.unpackbits(chunk, bitorder="little").reshape(-1, bit_width)
                vals = (bits.astype(np.int64) << np.arange(bit_width)).sum(axis=1)
            else:
                vals = np.zeros(groups * 8, dtype=np.int64)
            p += nbytes
            k = min(len(vals), count - i)
            res[i : i + k] = vals[:k]
            i += k
        else:  # RLE-run
            run = header >> 1
            v = int.from_bytes(buf[p : p + width_bytes], "little")
            p += width_bytes
            k = min(run, count - i)
            res[i : i + k] = v
            i += k
    return res


def read_parquet(path: str | Path, columns: list[str] | None = None) -> pd.DataFrame:
    buf = Path(path).read_bytes()
    footer_len = struct.unpack("<I", buf[-8:-4])[0]
    meta = _Thrift(buf, len(buf) - 8 - footer_len).struct()
    schema = meta[2][1:]
    optional = {e[4].decode(): e.get(3, 0) == 1 for e in schema}
    wanted = columns or [e[4].decode() for e in schema]
    chunks: dict[str, list[np.ndarray]] = {c: [] for c in wanted}
    for row_group in meta[4]:
        for column in row_group[1]:
            cm = column[3]
            name = b".".join(cm[3]).decode()
            if name not in chunks:
                continue
            codec, total, ptype = cm[4], cm[5], cm[1]
            p = cm.get(11) or cm[9]
            dictionary, values, got = None, [], 0
            while got < total:
                reader = _Thrift(buf, p)
                header = reader.struct()
                p = reader.p
                raw = buf[p : p + header[3]]
                p += header[3]
                if codec == 1:
                    raw = _snappy(raw)
                elif codec == 2:
                    raw = zlib.decompress(raw, 31)
                elif codec != 0:
                    raise ValueError(f"{name}: codec {codec} не поддержан")
                page_type = header[1]
                if page_type == 2:  # dictionary page
                    dictionary = np.frombuffer(
                        raw, dtype=_NP_TYPES[ptype], count=header[7][1]
                    )
                    continue
                if page_type == 0:  # data page v1
                    count, encoding = header[5][1], header[5][2]
                    offset = 0
                    if optional[name]:
                        offset = 4 + struct.unpack("<I", raw[:4])[0]
                elif page_type == 3:  # data page v2
                    h = header[8]
                    count, encoding = h[1], h[4]
                    offset = h[5] + h[6]
                else:
                    raise ValueError(f"page type {page_type}")
                data = raw[offset:]
                if encoding in (2, 8):
                    idx = _rle_bitpacked(data[1:], data[0], count)
                    values.append(dictionary[idx])
                elif encoding == 0:
                    values.append(
                        np.frombuffer(data, dtype=_NP_TYPES[ptype], count=count)
                    )
                else:
                    raise ValueError(f"{name}: encoding {encoding} не поддержан")
                got += count
            chunks[name].append(np.concatenate(values))
    return pd.DataFrame({c: np.concatenate(v) for c, v in chunks.items()})
