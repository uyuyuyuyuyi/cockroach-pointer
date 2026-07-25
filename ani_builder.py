"""
ani_builder.py — .ani 动画光标文件二进制构建器

纯 Python 构建 RIFF/ACON 格式的 .ani 动画光标文件。
每个动画帧使用 PNG 压缩的 .cur 格式内嵌，支持 Windows Vista+。
"""

import struct
import io
from PIL import Image


# ── 常量 ──────────────────────────────────────────────
# RIFF 块标识
RIFF_MAGIC = b"RIFF"
ACON_TYPE = b"ACON"
LIST_MAGIC = b"LIST"
FRAM_TYPE = b"fram"
INFO_TYPE = b"INFO"
ANIH_CHUNK = b"anih"
RATE_CHUNK = b"rate"


# ── .ani 核心结构 ─────────────────────────────────────

def pack_anihheader(
    num_frames: int,
    num_steps: int,
    width: int,
    height: int,
    bit_count: int = 32,
    num_planes: int = 1,
    display_rate_jiffies: int = 9,
    flags: int = 0,
) -> bytes:
    """
    打包 ANIHHEADER 结构 (36 bytes)。

    Args:
        num_frames: 帧总数 (cFrames)
        num_steps: 序列步骤数 (cSteps)，无 seq 块时等于帧数
        width: 光标宽度 (cx)
        height: 光标高度 (cy)
        bit_count: 每像素位数，PNG 帧固定 32
        num_planes: 色平面数，固定 1
        display_rate_jiffies: 默认显示速率 (1 jiffy = 1/60s)
        flags: 标志位 (0 = 正常)
    """
    return struct.pack(
        "<IIIIIIIII",
        36,              # cbSizeof
        num_frames,      # cFrames
        num_steps,       # cSteps
        width,           # cx
        height,          # cy
        bit_count,       # cBitCount
        num_planes,      # cPlanes
        display_rate_jiffies,
        flags,
    )


def pack_rate_chunk(frame_durations_ms: list[int]) -> bytes:
    """
    打包 rate 块数据（不含块头）。

    Args:
        frame_durations_ms: 每帧持续时间 (毫秒)

    Returns:
        rate 块数据体 (uint32 LE 数组)
    """
    rates = []
    for ms in frame_durations_ms:
        jiffies = max(1, round(ms / (1000.0 / 60.0)))
        rates.append(jiffies)
    return struct.pack("<" + "I" * len(rates), *rates)


# ── .cur 帧构建 ───────────────────────────────────────

def _make_cur_frame(
    png_data: bytes,
    hotspot_x: int,
    hotspot_y: int,
    width: int,
    height: int,
) -> bytes:
    """
    将 PNG 压缩数据包装为 .cur 格式帧。

    .cur 文件结构:
        0x00: reserved (2B) = 0
        0x02: type (2B) = 2 (cursor)
        0x04: count (2B) = 1
        0x06: 目录条目 (16B)
            - width (1B), height (1B), palette (1B)=0, reserved (1B)=0
            - hotspot_x (2B), hotspot_y (2B)
            - png_size (4B), png_offset (4B)
        其后: PNG 数据
    """
    png_size = len(png_data)
    png_offset = 6 + 16  # 头部 6B + 一个条目 16B

    buf = io.BytesIO()

    # ICO/CUR 头部
    buf.write(struct.pack("<H", 0))   # reserved
    buf.write(struct.pack("<H", 2))   # type: CUR
    buf.write(struct.pack("<H", 1))   # count: 1 image

    # 目录条目
    w = width if width < 256 else 0
    h = height if height < 256 else 0
    buf.write(struct.pack("<B", w))
    buf.write(struct.pack("<B", h))
    buf.write(struct.pack("<B", 0))   # palette colors (0 for PNG)
    buf.write(struct.pack("<B", 0))   # reserved
    buf.write(struct.pack("<h", hotspot_x))
    buf.write(struct.pack("<h", hotspot_y))
    buf.write(struct.pack("<I", png_size))
    buf.write(struct.pack("<I", png_offset))

    # PNG 数据
    buf.write(png_data)

    return buf.getvalue()


def pil_to_cur_frame(
    image: Image.Image,
    hotspot: tuple[int, int],
) -> bytes:
    """
    将 PIL RGBA Image 转换为 PNG 压缩的 .cur 帧字节。

    Args:
        image: PIL Image (将自动转换为 RGBA)
        hotspot: (x, y) 热点坐标

    Returns:
        .cur 格式帧字节
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # 序列化为 PNG 字节
    png_buf = io.BytesIO()
    image.save(png_buf, format="PNG", optimize=True)
    png_data = png_buf.getvalue()

    return _make_cur_frame(
        png_data=png_data,
        hotspot_x=hotspot[0],
        hotspot_y=hotspot[1],
        width=image.width,
        height=image.height,
    )


# ── RIFF 块写入工具 ────────────────────────────────────

def _write_chunk_header(buf: io.BytesIO, chunk_id: bytes, data_size: int) -> None:
    """写入 RIFF 块头: 4B ID + 4B size (不含填充)。"""
    buf.write(chunk_id)
    buf.write(struct.pack("<I", data_size))


def _write_chunk(buf: io.BytesIO, chunk_id: bytes, data: bytes) -> None:
    """写入完整 RIFF 块 (含头和数据)，自动 WORD 对齐填充。"""
    _write_chunk_header(buf, chunk_id, len(data))
    buf.write(data)
    if len(data) % 2 != 0:
        buf.write(b"\x00")  # WORD 对齐填充


def _write_list_header(buf: io.BytesIO, list_type: bytes, inner_size: int) -> None:
    """写入 LIST 块头: "LIST" + inner_size + list_type。"""
    buf.write(LIST_MAGIC)
    buf.write(struct.pack("<I", inner_size))
    buf.write(list_type)


# ── 可选 INFO 元数据 ───────────────────────────────────

def _build_info_chunks(title: str = "", author: str = "") -> bytes:
    """构建 RIFF INFO 子块数据体 (不含 LIST 头)。"""
    chunks = b""
    if title:
        encoded = title.encode("utf-16-le") + b"\x00\x00"
        chunks += b"INAM" + struct.pack("<I", len(encoded)) + encoded
    if author:
        encoded = author.encode("utf-16-le") + b"\x00\x00"
        chunks += b"IART" + struct.pack("<I", len(encoded)) + encoded
    return chunks


# ── 主导出函数 ─────────────────────────────────────────

def build_ani_file(
    frames: list[Image.Image],
    hotspots: list[tuple[int, int]],
    frame_durations_ms: list[int] | None = None,
    title: str = "",
    author: str = "",
) -> bytes:
    """
    从 PIL RGBA 图像构建完整的 .ani 动画光标文件。

    Args:
        frames: PIL Image 列表 (将自动转换为 RGBA)
        hotspots: 每帧的 (x, y) 热点列表
        frame_durations_ms: 每帧显示时间 (毫秒)，None=默认 100ms
        title: 可选光标标题
        author: 可选作者信息

    Returns:
        完整 .ani 文件字节

    Raises:
        ValueError: 帧数不一致
    """
    num_frames = len(frames)
    if num_frames == 0:
        raise ValueError("至少需要 1 帧")
    if len(hotspots) != num_frames:
        raise ValueError(f"hotspots 数量 ({len(hotspots)}) 与帧数 ({num_frames}) 不匹配")

    if frame_durations_ms is None:
        frame_durations_ms = [100] * num_frames
    elif len(frame_durations_ms) != num_frames:
        raise ValueError(
            f"frame_durations_ms 数量 ({len(frame_durations_ms)}) 与帧数 ({num_frames}) 不匹配"
        )

    width, height = frames[0].width, frames[0].height

    # ── 预渲染所有帧为 .cur 字节 ──
    cur_frames: list[bytes] = []
    for img, hs in zip(frames, hotspots):
        cur_frames.append(pil_to_cur_frame(img, hs))

    # ── 构建各块数据 ──
    anih_data = pack_anihheader(
        num_frames=num_frames,
        num_steps=num_frames,
        width=width,
        height=height,
        bit_count=32,
        num_planes=1,
        display_rate_jiffies=max(1, round(frame_durations_ms[0] / (1000.0 / 60.0))),
        flags=0x01,  # AF_ICON
    )

    rate_data = pack_rate_chunk(frame_durations_ms)

    # 构建 fram LIST 内部数据
    # 每帧包装为 RIFF 子块: "icon" (4B) + size (4B) + .cur数据 + 可能的 WORD 对齐填充
    fram_inner_parts: list[bytes] = []
    for cf in cur_frames:
        chunk_header = b"icon" + struct.pack("<I", len(cf))
        chunk_data = chunk_header + cf
        if len(cf) % 2 != 0:
            chunk_data += b"\x00"  # 子块数据 WORD 对齐
        fram_inner_parts.append(chunk_data)

    fram_data = b"".join(fram_inner_parts)
    # fram LIST 内部 = "fram" 类型ID (4B) + 所有 icon 子块
    fram_list_inner = 4 + len(fram_data)

    # INFO LIST (可选)
    info_chunks = _build_info_chunks(title, author)
    info_list_inner = 4 + len(info_chunks) if info_chunks else 0

    # ── 计算 RIFF 总大小 ──
    def _padded_size(data_len: int) -> int:
        return data_len + (1 if data_len % 2 != 0 else 0)

    total = 12  # RIFF header + ACON
    total += 8 + 36  # anih
    total += 8 + _padded_size(len(rate_data))  # rate
    total += 8 + _padded_size(fram_list_inner)  # fram LIST
    if info_chunks:
        total += 8 + _padded_size(info_list_inner)  # INFO LIST

    riff_data_size = total - 8

    # ── 写入 ──
    buf = io.BytesIO()

    buf.write(RIFF_MAGIC)
    buf.write(struct.pack("<I", riff_data_size))
    buf.write(ACON_TYPE)

    _write_chunk(buf, ANIH_CHUNK, anih_data)
    _write_chunk(buf, RATE_CHUNK, rate_data)

    # LIST "fram" — 帧以 icon 子块形式嵌入
    _write_list_header(buf, FRAM_TYPE, fram_list_inner)
    buf.write(fram_data)
    if fram_list_inner % 2 != 0:
        buf.write(b"\x00")

    # LIST "INFO" (optional)
    if info_chunks:
        _write_list_header(buf, INFO_TYPE, info_list_inner)
        buf.write(info_chunks)
        if info_list_inner % 2 != 0:
            buf.write(b"\x00")

    return buf.getvalue()


def save_ani_file(
    filepath: str,
    frames: list[Image.Image],
    hotspots: list[tuple[int, int]],
    frame_durations_ms: list[int] | None = None,
    title: str = "",
    author: str = "",
) -> None:
    """
    便捷函数：构建 .ani 文件并保存到磁盘。

    Args:
        filepath: 目标文件路径
        其余参数同 build_ani_file()
    """
    ani_bytes = build_ani_file(
        frames=frames,
        hotspots=hotspots,
        frame_durations_ms=frame_durations_ms,
        title=title,
        author=author,
    )
    with open(filepath, "wb") as f:
        f.write(ani_bytes)


# ── 测试入口 ──────────────────────────────────────────
if __name__ == "__main__":
    # 简单测试：生成两帧红蓝色块动画光标
    from PIL import Image, ImageDraw

    frames = []
    for i, color in enumerate([(255, 0, 0, 255), (0, 0, 255, 255)]):
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.polygon(
            [(0, 0), (24, 12), (12, 12), (12, 32), (0, 26)],
            fill=color,
        )
        frames.append(img)

    save_ani_file(
        "test_cursor.ani",
        frames=frames,
        hotspots=[(0, 0), (0, 0)],
        frame_durations_ms=[500, 500],
        title="Test Cursor",
    )
    print("已保存 test_cursor.ani (红蓝闪烁测试光标)")
