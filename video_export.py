"""Render the saved replay frames to PowerPoint-compatible H.264 MP4."""

import subprocess

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT, FPS = 1280, 720, 25


def write_mp4(path, data):
    font_name = "/System/Library/Fonts/Helvetica.ttc"
    fonts = [ImageFont.truetype(font_name, size) for size in (22, 31, 48)]
    small, medium, large = fonts

    def render(frame):
        image = Image.new("RGB", (WIDTH, HEIGHT), "#eef4f4")
        draw = ImageDraw.Draw(image)

        def text(x, y, value, font=medium):
            draw.text((x, y), value, font=font, fill="#142d39")

        def tile(x, y, w, h, color, label, outside=False):
            draw.rounded_rectangle((x, y, x+w, y+h), 10, fill=color,
                                   outline="#576e79" if outside else None, width=2)
            draw.multiline_text((x+w/2, y+h/2), label, anchor="mm", align="center",
                                font=small, fill="#142d39")

        text(56, 48, "Evacuation and synchronous decisions", large)
        text(58, 115, f"run_id: {data['run_id']}     n = {frame['n']}   /   t = {frame['t']}", small)
        text(58, 177, "Social ring")
        positions = frame["positions"]
        for i, (pid, s) in enumerate(zip(data["ids"], frame["intentions"])):
            outside = pid not in positions
            label = f"{pid} {'+' if s == 1 else '−'}" + ("\nExited" if outside else "")
            tile(58 + 124*i, 224, 112, 82, "#ccecea" if s == 1 else "#fbe1d9", label, outside)
        text(58, 359, "Corridor")
        at = {pos: pid for pid, pos in positions.items()}
        for i in range(1, data["length"] + 1):
            tile(58 + 124*(i-1), 407, 112, 83, "#ccecea" if i in at else "#e1eaed",
                 f"{i}\n{at.get(i, '·')}")
        tile(58 + 124*data["length"], 407, 112, 83, "#ffedb9",
             "Exit\n" + ", ".join(frame["exit_ids"]))
        phase = {"initial": "Initial state", "decision": "Decision update / positions held",
                 "movement": "Movement trial / positions updated"}[frame["phase"]]
        text(58, 545, phase)
        counts = frame["counts"]
        stop = counts or dict.fromkeys(("intention_stop", "exclusion_stop", "move"), "—")
        text(58, 612, f"Intention stop: {stop['intention_stop']}     "
             f"Exclusion stop: {stop['exclusion_stop']}     Moves: {stop['move']}     "
             f"Cumulative exits: {frame['cumulative_exits']}", small)
        return image.tobytes()

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
        "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
        "-framerate", f"{FPS}/13", "-i", "-", "-vf", f"fps={FPS}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
    ]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        for frame in data["frames"]:
            encoder.stdin.write(render(frame))
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("ffmpeg could not encode the replay")
