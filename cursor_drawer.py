"""
cursor_drawer.py — 白色蟑螂光标绘图引擎

使用 PIL ImageDraw 程序化绘制 48×48 白色蟑螂简笔画动画帧。
蟑螂朝上（纵向），8 帧爬行循环动画（三足步态）。
"""

import math
from PIL import Image, ImageDraw

# ── 常量 ──────────────────────────────────────────────
SIZE = 48                     # 光标尺寸 (px)
NUM_FRAMES = 8                # 动画帧数
FRAME_DURATION_MS = 150       # 每帧持续时间
HOTSPOT = (24, 28)            # 热点在身体正中心
BG_COLOR = (0, 0, 0, 0)      # 透明背景

# 蟑螂配色
BODY_FILL = (248, 248, 248, 235)      # 白色身体，微透明
BODY_OUTLINE = (160, 155, 150, 235)   # 浅灰轮廓
PRONOTUM_FILL = (235, 230, 225, 235)  # 前胸背板略深
HEAD_FILL = (245, 243, 240, 235)      # 头部
EYE_COLOR = (50, 45, 40, 240)         # 深色眼睛
LEG_COLOR = (220, 215, 210, 235)      # 腿部颜色
ANTENNA_COLOR = (230, 225, 220, 220)  # 触角略透明
CERCI_COLOR = (200, 195, 190, 220)    # 尾须

# 身体几何 — 纵向椭圆，长轴垂直
BODY_CENTER_X = 24.0          # 身体中心 X
BODY_CENTER_Y = 28.0          # 身体中心 Y（偏下为触角留空间）
BODY_RADIUS_X = 10.5          # 身体半宽 (水平) — 复刻照片：更宽胖
BODY_RADIUS_Y = 15.0          # 身体半高 (垂直)
HEAD_OFFSET_X = 0.0           # 头部在身体正上方
HEAD_OFFSET_Y = -18.0         # 头部 Y 偏移（身体中心上方）
HEAD_RADIUS = 3.4             # 头部半径 — 照片中头相对身体较小
PRONOTUM_WIDTH = 13.5         # 前胸背板宽度 — 照片中盾形明显

# ── 腿部定义 ──────────────────────────────────────────
# 每条腿: (名称, 附着角度°, 股节角度°, 股节长, 胫节长, 步态相位, 膝弯角度°)
# 附着角度: 在身体椭圆上的位置 (0°=右, 90°=下, -90°=上)
# 膝弯角度: 正值=逆时针, 负值=顺时针

LEGS = [
    # 左侧 (身体左边)
    # name         attach   base    fem_len tib_len phase knee_bend
    ("left_front",    -150,   -140,   10.5,    9.0,   0.5,    +28),
    ("left_mid",       180,    175,   11.5,   10.0,   0.0,    -32),
    ("left_back",      150,    140,   10.5,    9.5,   0.5,    -28),
    # 右侧 (身体右边)
    ("right_front",    -30,    -40,   10.5,    9.0,   0.0,    -28),
    ("right_mid",        0,      5,   11.5,   10.0,   0.5,    +32),
    ("right_back",      30,     40,   10.5,    9.5,   0.0,    +28),
]

# ── 触角定义 ────────────────────────────────────────────
# 每条触角: (头X偏移, 头Y偏移, 基础角度°, 长度, 分段数, 摆动相位)
# 照片特征: 从头部斜上 45° 外展, 末端向外弯成弧, 较长
ANTENNAE = [
    (HEAD_OFFSET_X - 2, HEAD_OFFSET_Y - 2, -135, 14, 4, 0.25),
    (HEAD_OFFSET_X + 2, HEAD_OFFSET_Y - 2,  -45, 14, 4, 0.75),
]


def _body_center(frame: int) -> tuple[float, float]:
    """计算身体中心在当前帧的位置（含轻微的纵向浮动）。"""
    phase = frame / NUM_FRAMES
    bob = math.sin(phase * 2 * math.pi) * 0.7  # ±0.7px 浮动
    return (BODY_CENTER_X, BODY_CENTER_Y + bob)


def _body_perimeter(body_cx: float, body_cy: float, angle_deg: float) -> tuple[float, float]:
    """计算身体椭圆边界上指定角度处的坐标。"""
    a = math.radians(angle_deg)
    return (
        body_cx + BODY_RADIUS_X * math.cos(a),
        body_cy + BODY_RADIUS_Y * math.sin(a),
    )


def _leg_endpoints(
    body_cx: float, body_cy: float,
    attach_angle_deg: float, base_angle_deg: float,
    femur_len: float, tibia_len: float,
    phase: float, knee_bend_deg: float, frame: int,
) -> list[tuple[float, float]]:
    """
    计算一条腿的关节点坐标。
    Returns: [附着点, 膝关节, 足尖]
    """
    anim_phase = (frame / NUM_FRAMES + phase) % 1.0
    swing = math.sin(anim_phase * 2 * math.pi) * 10.0  # ±10° 股节摆动
    femur_angle = math.radians(base_angle_deg + swing)

    # 身体椭圆上的附着点
    attach_x, attach_y = _body_perimeter(body_cx, body_cy, attach_angle_deg)

    # 膝关节
    knee_x = attach_x + math.cos(femur_angle) * femur_len
    knee_y = attach_y + math.sin(femur_angle) * femur_len

    # 胫节弯曲 — 使用预定义的膝弯角 + 小幅动画摆动
    anim_bend = math.cos(anim_phase * 2 * math.pi) * 6
    tibia_angle = femur_angle + math.radians(knee_bend_deg + anim_bend)

    foot_x = knee_x + math.cos(tibia_angle) * tibia_len
    foot_y = knee_y + math.sin(tibia_angle) * tibia_len

    return [(attach_x, attach_y), (knee_x, knee_y), (foot_x, foot_y)]


def _antenna_points(
    body_cx: float, body_cy: float,
    base_angle_deg: float, length: float, segments: int,
    phase: float, frame: int,
) -> list[tuple[float, float]]:
    """计算触角的控制点列表（从头部向上方弯曲）。"""
    anim_phase = (frame / NUM_FRAMES + phase) % 1.0
    head_x = body_cx + HEAD_OFFSET_X
    head_y = body_cy + HEAD_OFFSET_Y

    points = [(head_x, head_y)]
    seg_len = length / segments
    angle = math.radians(base_angle_deg)

    for i in range(segments):
        wave = math.sin(anim_phase * 2 * math.pi + i * 1.2) * 7.0
        # 触角逐渐向外侧弯曲
        curve_sign = 1 if base_angle_deg > -90 else -1
        curve = (i / segments) * 20
        seg_angle = angle + math.radians(curve * curve_sign)
        seg_angle += math.radians(wave * 0.35)

        px = points[-1][0] + math.cos(seg_angle) * seg_len
        py = points[-1][1] + math.sin(seg_angle) * seg_len
        points.append((px, py))

    return points


def draw_frame(frame: int) -> Image.Image:
    """
    绘制单帧蟑螂图像（纵向，头朝上）。

    Args:
        frame: 帧编号 (0 ~ NUM_FRAMES-1)

    Returns:
        PIL Image, RGBA 模式, SIZE×SIZE
    """
    img = Image.new("RGBA", (SIZE, SIZE), BG_COLOR)
    draw = ImageDraw.Draw(img)

    body_cx, body_cy = _body_center(frame)

    # ── 1. 绘制后腿（先画远侧，近侧遮盖） ──
    # 右侧腿在蟑螂"下方"（从俯视角度），先画
    leg_order = [3, 4, 5, 0, 1, 2]  # 右侧 3-5 先，左侧 0-2 后
    for idx in leg_order:
        _name, a_ang, b_ang, flen, tlen, ph, kb = LEGS[idx]
        segs = _leg_endpoints(body_cx, body_cy,
                              a_ang, b_ang, flen, tlen, ph, kb, frame)
        for s in range(len(segs) - 1):
            draw.line([segs[s], segs[s + 1]], fill=LEG_COLOR, width=2)
        # 足尖
        draw.ellipse(
            (segs[-1][0] - 1.5, segs[-1][1] - 1.5,
             segs[-1][0] + 1.5, segs[-1][1] + 1.5),
            fill=LEG_COLOR,
        )

    # ── 2. 绘制尾须 (cerci) — 身体尾端，向两侧分开伸出 ──
    # 照片特征: 尾须较长, 明显向两侧外分
    c_phase = frame / NUM_FRAMES
    c_swing = math.sin(c_phase * 2 * math.pi) * 4.0
    rear_x = body_cx
    rear_y = body_cy + BODY_RADIUS_Y - 3
    for side in (-1, 1):
        c_angle = math.radians(90 + side * (28 + c_swing))
        end_x = rear_x + math.cos(c_angle) * 9
        end_y = rear_y + math.sin(c_angle) * 9
        draw.line([(rear_x, rear_y), (end_x, end_y)],
                  fill=CERCI_COLOR, width=1)

    # ── 3. 绘制身体（纵向椭圆） ──
    body_bbox = (
        body_cx - BODY_RADIUS_X, body_cy - BODY_RADIUS_Y,
        body_cx + BODY_RADIUS_X, body_cy + BODY_RADIUS_Y,
    )
    draw.ellipse(body_bbox, fill=BODY_FILL, outline=BODY_OUTLINE, width=1)

    # ── 4. 绘制前胸背板 (pronotum) — 身体上方的盾形 ──
    pw2 = PRONOTUM_WIDTH / 2
    pronotum_bbox = (
        body_cx - pw2, body_cy - BODY_RADIUS_Y * 0.85,
        body_cx + pw2, body_cy - BODY_RADIUS_Y * 0.15,
    )
    draw.ellipse(pronotum_bbox, fill=PRONOTUM_FILL, outline=BODY_OUTLINE, width=1)

    # ── 5. 绘制头部 — 身体顶端 ──
    head_x = body_cx + HEAD_OFFSET_X
    head_y = body_cy + HEAD_OFFSET_Y + 1
    head_bbox = (
        head_x - HEAD_RADIUS, head_y - HEAD_RADIUS,
        head_x + HEAD_RADIUS, head_y + HEAD_RADIUS,
    )
    draw.ellipse(head_bbox, fill=HEAD_FILL, outline=BODY_OUTLINE, width=1)

    # ── 6. 绘制眼睛 — 头部两侧靠上 ──
    eye_r = 1.1
    for eye_dx in (-2.0, 2.0):
        eye_bbox = (
            head_x + eye_dx - eye_r, head_y - 1.5 - eye_r,
            head_x + eye_dx + eye_r, head_y - 1.5 + eye_r,
        )
        draw.ellipse(eye_bbox, fill=EYE_COLOR)

    # ── 7. 绘制触角 — 从头部向上方弯曲延伸 ──
    for base_dx, base_dy, base_ang, length, segs, phase in ANTENNAE:
        ant_x = body_cx + base_dx
        ant_y = body_cy + base_dy
        pts = _antenna_points(body_cx, body_cy, base_ang, length, segs, phase, frame)
        pts[0] = (ant_x, ant_y)
        for s in range(len(pts) - 1):
            w = max(1, int(2.5 - s * 0.8))
            draw.line([pts[s], pts[s + 1]], fill=ANTENNA_COLOR, width=w)
        tip = pts[-1]
        draw.ellipse(
            (tip[0] - 1, tip[1] - 1, tip[0] + 1, tip[1] + 1),
            fill=ANTENNA_COLOR,
        )

    # ── 8. 身体纹理: 翅缝线 + 腹节横纹 (复刻照片特征) ──
    # 翅缝: 身体中央一条纵向浅缝线 (照片中两片翅闭合的中缝)
    seam_color = (200, 196, 190, 140)
    seam_y0 = body_cy - BODY_RADIUS_Y * 0.55
    seam_y1 = body_cy + BODY_RADIUS_Y * 0.88
    draw.line([(body_cx, seam_y0), (body_cx, seam_y1)],
              fill=seam_color, width=1)
    # 腹节: 身体下半部 3 条弧形节段线 (照片腹部节纹)
    seg_color = (190, 186, 180, 120)
    for i in range(1, 4):
        seg_y = body_cy + BODY_RADIUS_Y * (0.10 + 0.24 * i)
        seg_half = BODY_RADIUS_X * (1.0 - 0.18 * i)
        draw.arc(
            (body_cx - seg_half, seg_y - 2, body_cx + seg_half, seg_y + 2),
            start=0, end=180, fill=seg_color, width=1,
        )

    # ── 9. 身体高光（纵向条状立体感） ──
    hl_w = BODY_RADIUS_X * 0.35
    hl_h = BODY_RADIUS_Y * 0.55
    highlight_bbox = (
        body_cx - hl_w, body_cy - hl_h,
        body_cx + hl_w, body_cy + hl_h,
    )
    draw.ellipse(highlight_bbox, fill=(255, 255, 255, 55))

    return img


def generate_frames() -> list[Image.Image]:
    """
    生成全部动画帧。

    Returns:
        包含 NUM_FRAMES 个 PIL Image 的列表
    """
    return [draw_frame(i) for i in range(NUM_FRAMES)]


def generate_tray_icon(size: int = 64) -> Image.Image:
    """
    生成系统托盘图标（迷你蟑螂）。

    Args:
        size: 图标尺寸 (默认 64×64)

    Returns:
        PIL Image, RGBA 模式
    """
    # 简单地缩放第 0 帧 + 画到更大画布上居中
    frame0 = draw_frame(0)

    # 创建方形画布
    icon = Image.new("RGBA", (size, size), BG_COLOR)
    # 居中放置蟑螂（稍微放大）
    scaled = frame0.resize((int(size * 0.85), int(size * 0.85)), Image.LANCZOS)
    offset_x = (size - scaled.width) // 2
    offset_y = (size - scaled.height) // 2
    icon.paste(scaled, (offset_x, offset_y), scaled)

    # 添加一个淡色圆形背景
    bg_draw = ImageDraw.Draw(icon)
    margin = 3
    bg_draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=(60, 55, 50, 200),
    )

    # 把蟑螂再贴到背景上面
    icon.paste(scaled, (offset_x, offset_y), scaled)

    return icon


# ── 测试入口 ──────────────────────────────────────────
if __name__ == "__main__":
    frames = generate_frames()
    print(f"生成了 {len(frames)} 帧动画 (每帧 {SIZE}×{SIZE})")

    # 保存单帧预览
    frames[0].save("cockroach_frame0_preview.png")
    print("已保存 cockroach_frame0_preview.png 供预览")

    icon = generate_tray_icon()
    icon.save("cockroach_tray_icon.png")
    print("已保存 cockroach_tray_icon.png 供预览")
