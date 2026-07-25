"""临时测试脚本：生成蟑螂 .ani 光标文件和资源。"""
from cursor_drawer import generate_frames, generate_tray_icon, NUM_FRAMES, FRAME_DURATION_MS, HOTSPOT
from ani_builder import save_ani_file
import os

os.makedirs("resources", exist_ok=True)

frames = generate_frames()
hotspots = [HOTSPOT] * NUM_FRAMES
durations = [FRAME_DURATION_MS] * NUM_FRAMES

save_ani_file(
    "resources/cockroach.ani",
    frames=frames,
    hotspots=hotspots,
    frame_durations_ms=durations,
    title="Cockroach Cursor",
    author="Cursor Changer",
)
size = os.path.getsize("resources/cockroach.ani")
print(f"Built cockroach.ani: {size} bytes ({size/1024:.1f} KB)")

icon = generate_tray_icon(64)
icon.save("resources/tray_icon.png")
print("Saved tray_icon.png")

frames[0].save("cockroach_frame0_preview.png")
print("Saved preview")

# 验证 .ani 文件头
with open("resources/cockroach.ani", "rb") as f:
    header = f.read(12)
    print(f"ANI header: {header}")
    assert header[:4] == b"RIFF", "Not a valid RIFF file!"
    assert header[8:12] == b"ACON", "Not a valid ANI file!"
    print("ANI format validation: PASSED")
