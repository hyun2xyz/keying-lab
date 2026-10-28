#!/usr/bin/env python3
"""Render independent live-action keying reels; never infer a matte or alter inputs.

Python 3.10+, NumPy, Pillow, FFmpeg/FFprobe with libx264 are required. Example:
  python render_reels.py --manifest ../manifest.json --output-dir ../reels

Contract: 96 RGB8 source PNGs and matching straight RGBA8 prediction PNGs,
case-specific width/height, square pixels, prepared at 24 fps, sRGB RGB and
linear alpha. GT is optional;
without an actual gt_rgba_dir no ground truth or error measurements are made.
Paths must stay inside the manifest directory. Files are matched by stem and
naturally ordered. Manifest fps is the prepared PNG sequence rate (24);
original camera rates may differ, and their ingest mapping belongs to the
source provenance. Output is 30 fps and preserves the four-second sequence.
Output n=0..359 uses input index (n*24//30) % 96. This holds existing source
samples during 24->30 conversion, without synthesizing intermediate footage.
Stages n=0..119: full; 120..239: nearest-neighbor native ROI; 240..299: ROI
model alpha; 300..359: ROI checker composite. Each case is exactly 12 s,
three four-second source loops. Any case count is supported; eight cases
concatenate to exactly 96 s / 2880 output samples.

RGB is decoded with the sRGB EOTF, composited with linear alpha over an sRGB
gray checker, then encoded with the sRGB OETF. Only display scaling follows.
Alpha diagnostics map alpha8 directly to gray display codes. The encoder
explicitly converts full-range RGB to BT.709-matrix, limited-range YUV420p and
declares BT.709 primaries, IEC 61966-2-1 (sRGB) transfer, square pixels. This is
an sRGB-transfer video, not a BT.709-transfer video. Chroma subsampling and
H.264 are lossy; the native input/metric images remain unchanged.

Each case's exact manifest credit string is burned into every output frame.
No common license is assumed across the independent sources.
No font is copied. Each MP4 is checked for sample clocks, color tags, and full
decode. A receipt binds input SHA256 values and commands. Visual approval is
separate. Existing deliverables are never overwritten. No audio is added.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import glob
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS, SOURCE_FPS = 1080, 1350, 30, 24
PANEL_SIZE = (1080, 608)
TOP_Y, BOTTOM_Y, FOOTER_Y = 70, 698, 1306
SOURCE_FRAMES, OUTPUT_FRAMES = 96, 360
LOOP_OUTPUT_FRAMES = 120
EXCLUDED_FINAL_CASE_IDS = frozenset({"02_dance"})
COLOR_FILTER = (
    "setparams=range=full:color_primaries=bt709:color_trc=iec61966-2-1:colorspace=gbr,"
    "scale=in_color_matrix=bt709:out_color_matrix=bt709:in_range=pc:out_range=tv,"
    "format=yuv420p,setsar=1,"
    "setparams=range=limited:color_primaries=bt709:color_trc=iec61966-2-1:colorspace=bt709"
)
SRGB_TO_LINEAR = np.where(
    np.arange(256, dtype=np.float32) / 255.0 <= 0.04045,
    np.arange(256, dtype=np.float32) / (255.0 * 12.92),
    ((np.arange(256, dtype=np.float32) / 255.0 + 0.055) / 1.055) ** 2.4,
)


class RenderError(RuntimeError):
    pass


def combined_name(case_count: int) -> str:
    if case_count < 1:
        raise RenderError("At least one case is required")
    return f"keying_breakdown_real{case_count}_1080x1350.mp4"


def reject_excluded_case(entry: dict[str, Any]) -> None:
    """Honor the explicit user exclusion while retaining its archived files."""
    case_id = str(entry.get("id", "")).casefold()
    paths = (str(entry.get(key, "")).replace("\\", "/").casefold().split("/")
             for key in ("source_dir", "pred_rgba_dir"))
    if case_id in EXCLUDED_FINAL_CASE_IDS or any(
            excluded in parts for parts in paths for excluded in EXCLUDED_FINAL_CASE_IDS):
        raise RenderError("02_dance was excluded by the user; keep its files archived and omit it from the final manifest")


@dataclass
class Case:
    id: str
    title: str
    width: int
    height: int
    credit: str
    roi: tuple[int, int, int, int]
    metrics: dict[str, Any]
    source: list[Path]
    pred: list[Path]
    gt: list[Path] | None
    inputs: list[dict[str, str]]


def natural_key(path: Path) -> list[Any]:
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", path.name)]


def contained_directory(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise RenderError("Image directory must be a nonempty relative path")
    relative = Path(value)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise RenderError(f"Image directory must stay inside the manifest directory: {value}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise RenderError(f"Missing or escaping image directory: {value}")
    return path


def png_paths(directory: Path) -> list[Path]:
    files = sorted((p for p in directory.iterdir()
                    if p.is_file() and p.suffix.casefold() == ".png"), key=natural_key)
    if len(files) != SOURCE_FRAMES:
        raise RenderError(f"{directory}: expected {SOURCE_FRAMES} PNGs, got {len(files)}")
    if len({p.stem.casefold() for p in files}) != len(files):
        raise RenderError(f"Duplicate image stems: {directory}")
    return files


def validate_png(path: Path, mode: str, expected_size: tuple[int, int] | None = None) -> str:
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise RenderError(f"Invalid PNG signature/IHDR: {path}")
    width, height, depth, color_type, compression, filt, interlace = struct.unpack(
        ">IIBBBBB", data[16:29])
    expected_type = 2 if mode == "RGB" else 6
    if (width < 1 or height < 1 or (expected_size is not None and (width, height) != expected_size)
            or depth != 8 or color_type != expected_type):
        raise RenderError(f"{path}: expected {mode}8 {expected_size or 'positive dimensions'}, got "
                          f"{width}x{height}, depth={depth}, PNG type={color_type}")
    if compression or filt or interlace not in (0, 1):
        raise RenderError(f"Unsupported PNG encoding: {path}")
    try:
        with Image.open(io.BytesIO(data)) as check:
            check.verify()  # Includes PNG chunk CRC checks.
        with Image.open(io.BytesIO(data)) as check:
            check.load()  # All image samples must decode, not just headers.
            if check.mode != mode or getattr(check, "n_frames", 1) != 1:
                raise RenderError(f"Expected a single {mode} PNG: {path}")
    except (OSError, SyntaxError, ValueError) as exc:
        raise RenderError(f"PNG validation failed: {path}: {exc}") from exc
    return hashlib.sha256(data).hexdigest()


def load_project(manifest_path: Path) -> tuple[list[Case], dict[str, Any]]:
    manifest_path = manifest_path.resolve(strict=True)
    raw = manifest_path.read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(document, dict) or Fraction(str(document.get("fps", 0))) != SOURCE_FPS:
        raise RenderError("Manifest fps must be exactly 24 (prepared four-second source sequence)")
    if Fraction(str(document.get("output_fps", FPS))) != FPS:
        raise RenderError("Output fps must be exactly 30")
    entries = document.get("cases")
    if not isinstance(entries, list) or not entries:
        raise RenderError("Manifest cases must be a nonempty list")
    cases: list[Case] = []
    ids: set[str] = set()
    for entry in entries:
        reject_excluded_case(entry)
        case_id = entry.get("id", "")
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", case_id):
            raise RenderError(f"Unsafe case id: {case_id!r}")
        if case_id.casefold() in ids:
            raise RenderError(f"Duplicate case id: {case_id}")
        ids.add(case_id.casefold())
        title = entry.get("title", case_id)
        if not isinstance(title, str) or not title or any(ord(c) < 32 for c in title):
            raise RenderError(f"Invalid title for {case_id}")
        width, height = entry.get("width"), entry.get("height")
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in (width, height)):
            raise RenderError(f"{case_id}: width and height must be positive integers")
        native_size = (width, height)
        credit = entry.get("credit")
        if (not isinstance(credit, str) or not credit.strip()
                or any(ord(c) < 32 for c in credit)):
            raise RenderError(f"{case_id}: a nonempty single-line case.credit string is required")
        if (entry.get("frames") != SOURCE_FRAMES
                or Fraction(str(entry.get("fps", SOURCE_FPS))) != SOURCE_FPS):
            raise RenderError(f"{case_id}: expected 96 prepared source samples at exactly 24 fps")
        if entry.get("pixel_aspect_ratio", "1:1") != "1:1":
            raise RenderError(f"{case_id}: this preset requires square source pixels")
        roi = entry.get("roi")
        if (not isinstance(roi, list) or len(roi) != 4
                or any(not isinstance(v, int) or isinstance(v, bool) for v in roi)):
            raise RenderError(f"{case_id}: roi must be integer [x,y,width,height]")
        x, y, w, h = roi
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise RenderError(f"{case_id}: roi is outside the {width}x{height} source PNG")
        metrics = entry.get("metrics", {})
        if not isinstance(metrics, dict):
            raise RenderError(f"{case_id}: metrics must be an object")
        source_paths, prediction_paths = [
            png_paths(contained_directory(manifest_path.parent, entry.get(key)))
            for key in ("source_dir", "pred_rgba_dir")]
        gt_paths = (png_paths(contained_directory(manifest_path.parent, entry["gt_rgba_dir"]))
                    if entry.get("gt_rgba_dir") is not None else None)
        sequences = [source_paths, prediction_paths] + ([gt_paths] if gt_paths is not None else [])
        if any([p.stem for p in paths] != [p.stem for p in source_paths] for paths in sequences[1:]):
            raise RenderError(f"{case_id}: source/prediction/optional GT image stems must match exactly")
        if gt_paths is None:
            forbidden = ("mae", "edge_mae", "mse", "psnr", "ssim", "iou", "binary_iou_at_0p5",
                         "worst_roi_mae", "opaque_hole_fraction_below_0p95", "background_mean_alpha",
                         "background_false_positive_fraction_at_0p02")
            if any(metrics.get(key) is not None for key in forbidden):
                raise RenderError(f"{case_id}: GT error metrics cannot be supplied without actual GT images")
        inputs = []
        for frame_index, (source, pred) in enumerate(zip(source_paths, prediction_paths)):
            image_identity = {
                "stem": source.stem,
                "source": source.relative_to(manifest_path.parent).as_posix(),
                "source_sha256": validate_png(source, "RGB", native_size),
                "prediction": pred.relative_to(manifest_path.parent).as_posix(),
                "prediction_sha256": validate_png(pred, "RGBA", native_size),
            }
            if gt_paths is not None:
                gt = gt_paths[frame_index]
                image_identity.update({"ground_truth": gt.relative_to(manifest_path.parent).as_posix(),
                                       "ground_truth_sha256": validate_png(gt, "RGBA", native_size)})
            inputs.append(image_identity)
        cases.append(Case(case_id, title, width, height, credit, tuple(roi), metrics,
                          source_paths, prediction_paths, gt_paths, inputs))
        print(f"Validated {case_id}: 96 synchronized RGB8/RGBA8 samples; "
              f"GT={'provided' if gt_paths is not None else 'none'}", flush=True)
    return cases, {"manifest": str(manifest_path), "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def resolve_font(value: str | None) -> Path:
    if value:
        path = Path(value).resolve(strict=True)
        ImageFont.truetype(str(path), 24)
        return path
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path(sys.executable).parent / "Lib/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf",
    ]
    candidates += [Path(p) for p in glob.glob(
        "C:/Program Files/Side Effects Software/*/houdini/fonts/DejaVuSans.ttf")]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise RenderError("No DejaVu/Liberation font found; supply an installed licensed font with --font")


class Fonts:
    def __init__(self, path: Path):
        self.path = path
        self.cache: dict[int, ImageFont.FreeTypeFont] = {}

    def get(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self.cache:
            self.cache[size] = ImageFont.truetype(str(self.path), size)
        return self.cache[size]


def linear_to_srgb8(linear: np.ndarray) -> np.ndarray:
    linear = np.clip(linear, 0.0, 1.0)
    encoded = np.where(linear <= 0.0031308, 12.92 * linear,
                       1.055 * np.maximum(linear, 0.0) ** (1.0 / 2.4) - 0.055)
    return np.clip(np.rint(encoded * 255.0), 0, 255).astype(np.uint8)


def checker_tile(size: tuple[int, int]) -> int:
    """About 27 output pixels per tile in full view, stable in native ROI crops."""
    scale = min(PANEL_SIZE[0] / size[0], PANEL_SIZE[1] / size[1])
    return max(1, round(27 / scale))


def checker_rgb(size: tuple[int, int]) -> np.ndarray:
    yy, xx = np.indices((size[1], size[0]))
    tile = checker_tile(size)
    values = np.where(((xx // tile + yy // tile) & 1) == 0, 176, 208).astype(np.uint8)
    return np.repeat(values[..., None], 3, axis=2)


@lru_cache(maxsize=1)
def checker_linear(size: tuple[int, int]) -> np.ndarray:
    return SRGB_TO_LINEAR[checker_rgb(size)]


def composite_rgba(rgba: np.ndarray) -> Image.Image:
    alpha = rgba[..., 3:4].astype(np.float32) / 255.0
    background = checker_linear((rgba.shape[1], rgba.shape[0]))
    linear = SRGB_TO_LINEAR[rgba[..., :3]] * alpha + background * (1.0 - alpha)
    return Image.fromarray(linear_to_srgb8(linear))


def fitted_panel(image: Image.Image, roi: tuple[int, int, int, int] | None
                 ) -> tuple[Image.Image, float, tuple[int, int]]:
    if roi:
        x, y, w, h = roi
        image = image.crop((x, y, x + w, y + h))
    scale = min(PANEL_SIZE[0] / image.width, PANEL_SIZE[1] / image.height)
    size = (min(PANEL_SIZE[0], round(image.width * scale)),
            min(PANEL_SIZE[1], round(image.height * scale)))
    image = image.resize(size, Image.Resampling.NEAREST if roi else Image.Resampling.LANCZOS)
    panel = Image.new("RGB", PANEL_SIZE, (224, 224, 224))
    offset = ((PANEL_SIZE[0] - size[0]) // 2, (PANEL_SIZE[1] - size[1]) // 2)
    panel.paste(image, offset)
    return panel, scale, offset


def badge(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], fonts: Fonts,
          right: bool = False, size: int = 21) -> None:
    font = fonts.get(size)
    width = math.ceil(draw.textlength(text, font=font)) + 22
    x, y = xy
    if right:
        x -= width
    draw.rectangle((x, y, x + width, y + 34), fill=(15, 15, 15))
    draw.text((x + 11, y + 5), text, font=font, fill="white", stroke_width=0)


def fitted_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fonts: Fonts,
                max_width: int, size: int, fill: str = "black") -> None:
    while size > 12 and draw.textlength(text, font=fonts.get(size)) > max_width:
        size -= 1
    draw.text(xy, text, font=fonts.get(size), fill=fill)


def render_frame(case: Case, output_index: int, case_number: int, total_cases: int,
                 fonts: Fonts) -> Image.Image:
    if not 0 <= output_index < OUTPUT_FRAMES:
        raise RenderError(f"Output frame out of range: {output_index}")
    source_index, loop = source_clock(output_index)
    with Image.open(case.source[source_index]) as source_file:
        source = source_file.copy()
    with Image.open(case.pred[source_index]) as pred_file:
        rgba = np.asarray(pred_file, dtype=np.uint8)
    zoomed = output_index >= 120
    is_alpha = 240 <= output_index < 300
    result = (Image.fromarray(np.repeat(rgba[..., 3:4], 3, axis=2)) if is_alpha
              else composite_rgba(rgba))
    roi = case.roi if zoomed else None
    source_panel, scale, offset = fitted_panel(source, roi)
    result_panel, _, _ = fitted_panel(result, roi)
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    image.paste(source_panel, (0, TOP_Y))
    image.paste(result_panel, (0, BOTTOM_Y))
    draw = ImageDraw.Draw(image)
    fitted_text(draw, (23, 17), f"{case_number:02d} / {total_cases:02d}   {case.title}",
                fonts, 835, 29)
    draw.text((918, 25), f"REAL{total_cases} KEYING", font=fonts.get(17), fill="black")
    badge(draw, "SOURCE", (22, TOP_Y + 17), fonts)
    badge(draw, "KEYED RESULT", (22, BOTTOM_Y + 17), fonts)
    view = f"NATIVE ROI {scale:.2f}x" if zoomed else f"FULL FRAME {scale:.2f}x"
    badge(draw, f"{view}  |  LOOP {loop}/3", (1058, TOP_Y + 17), fonts, right=True, size=18)
    stage = "MODEL ALPHA" if is_alpha else ("ROI / CHECKER" if zoomed else "LINEAR / CHECKER")
    badge(draw, stage, (1058, BOTTOM_Y + 17), fonts, right=True, size=18)
    if not zoomed:
        x, y, w, h = case.roi
        for panel_y in (TOP_Y, BOTTOM_Y):
            box = (offset[0] + round(x * scale), panel_y + offset[1] + round(y * scale),
                   offset[0] + round((x + w) * scale) - 1,
                   panel_y + offset[1] + round((y + h) * scale) - 1)
            draw.rectangle(box, outline="black", width=3)
            draw.rectangle((box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1),
                           outline="white", width=1)
    gt_note = " | NO GT ALPHA" if case.gt is None else ""
    footer_left = ("MODEL ALPHA" if is_alpha else "Linear-light sRGB composite") + gt_note
    fitted_text(draw, (22, FOOTER_Y + 2), footer_left, fonts, 535, 14)
    clock = (f"SRC24 {source_index:02d}/95 {source_index / SOURCE_FPS:05.3f}s"
             f" | OUT30 {output_index:03d}/359 | HOLD")
    clock_width = draw.textlength(clock, font=fonts.get(14))
    draw.text((1058 - clock_width, FOOTER_Y + 2), clock, font=fonts.get(14), fill="black")
    credit_size = 18
    while credit_size > 14 and draw.textlength(case.credit, font=fonts.get(credit_size)) > WIDTH - 44:
        credit_size -= 1
    credit_width = draw.textlength(case.credit, font=fonts.get(credit_size))
    if credit_width > WIDTH - 44:
        raise RenderError(f"{case.id}: case.credit is too long for a readable footer; shorten the attribution text")
    draw.text(((WIDTH - credit_width) / 2, FOOTER_Y + 21), case.credit,
              font=fonts.get(credit_size), fill="black")
    return image


def source_clock(output_index: int) -> tuple[int, int]:
    """Exact integer sample-hold: no float time rounding or optical interpolation."""
    if not 0 <= output_index < OUTPUT_FRAMES:
        raise RenderError(f"Output frame out of range: {output_index}")
    return ((output_index * SOURCE_FPS // FPS) % SOURCE_FRAMES,
            output_index // LOOP_OUTPUT_FRAMES + 1)


def encoder_command(ffmpeg: str, output: Path, crf: int, preset: str) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
            "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
            "-framerate", str(FPS), "-i", "pipe:0", "-map", "0:v:0", "-an", "-vf", COLOR_FILTER,
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-bf", "0", "-fps_mode", "passthrough", "-frames:v", str(OUTPUT_FRAMES),
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "iec61966-2-1", "-video_track_timescale", "30000", "-movflags", "+faststart",
            str(output)]


def encode_case(case: Case, index: int, total: int, fonts: Fonts, output: Path,
                ffmpeg: str, crf: int, preset: str) -> list[str]:
    command = encoder_command(ffmpeg, output, crf, preset)
    log_path = output.with_suffix(".encode.log")
    with log_path.open("xb") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            assert process.stdin is not None
            for n in range(OUTPUT_FRAMES):
                process.stdin.write(render_frame(case, n, index, total, fonts).tobytes())
            process.stdin.close()
            return_code = process.wait()
        except BaseException:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            process.terminate()
            process.wait()
            raise
    if return_code:
        raise RenderError(f"Encoder failed ({return_code}); preserved output/log: {output}, {log_path}")
    return command


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RenderError(f"Command failed ({result.returncode}): {command!r}\n{result.stderr[-6000:]}")
    return result


def verify_video(path: Path, expected_frames: int, ffmpeg: str, ffprobe: str) -> dict[str, Any]:
    probe_cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_packets",
                 "-show_streams", "-show_format", "-of", "json", str(path)]
    probe = json.loads(run_checked(probe_cmd).stdout)
    stream = probe["streams"][0]
    expected = {"width": WIDTH, "height": HEIGHT, "pix_fmt": "yuv420p",
                "sample_aspect_ratio": "1:1", "color_range": "tv", "color_space": "bt709",
                "color_transfer": "iec61966-2-1", "color_primaries": "bt709"}
    wrong = {key: {"expected": value, "actual": stream.get(key)}
             for key, value in expected.items() if stream.get(key) != value}
    if wrong:
        raise RenderError(f"Published output format/color mismatch in {path}: {wrong}")
    if Fraction(stream["time_base"]) != Fraction(1, 30000):
        raise RenderError(f"Unexpected sample time base in {path}: {stream['time_base']}")
    for field in ("r_frame_rate", "avg_frame_rate"):
        if Fraction(stream[field]) != FPS:
            raise RenderError(f"Wrong {field} in {path}: {stream[field]}")
    packets = probe.get("packets", [])
    if len(packets) != expected_frames or int(stream.get("nb_frames", -1)) != expected_frames:
        raise RenderError(f"Wrong packet/frame count in {path}: {len(packets)}, {stream.get('nb_frames')}")
    for n, packet in enumerate(packets):
        if any(int(packet.get(key, -1)) != value for key, value in
               (("pts", n * 1000), ("dts", n * 1000), ("duration", 1000))):
            raise RenderError(f"Unexpected encoded sample clock in {path}, sample {n}: {packet}")
    if int(stream.get("duration_ts", -1)) != expected_frames * 1000:
        raise RenderError(f"Wrong MP4 sample-table duration in {path}: {stream.get('duration_ts')}")
    if abs(float(probe["format"]["duration"]) - expected_frames / FPS) > 0.000001:
        raise RenderError(f"Wrong container duration in {path}: {probe['format']['duration']}")
    decode_cmd = [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-err_detect", "explode",
                  "-i", str(path), "-map", "0:v:0", "-an", "-progress", "pipe:1", "-f", "null", "-"]
    decoded = run_checked(decode_cmd)
    frames = re.findall(r"^frame=(\d+)\s*$", decoded.stdout, flags=re.MULTILINE)
    if not frames or int(frames[-1]) != expected_frames:
        raise RenderError(f"Full decoder returned wrong frame count for {path}: {frames[-1:]}")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size, "frames": expected_frames, "duration_seconds": expected_frames / FPS,
            "time_base": "1/30000", "sample_duration_ticks": 1000, "all_packet_pts_dts_duration_checked": True,
            "full_decode_frames": int(frames[-1]), "published_tags": expected,
            "probe_command": probe_cmd, "decode_command": decode_cmd}


def write_contact_sheet(case: Case, index: int, total: int, fonts: Fonts, path: Path) -> None:
    sheet = Image.new("RGB", (1080, 1350), "white")
    for cell, n in enumerate((0, 120, 240, 300)):
        sample = render_frame(case, n, index, total, fonts).resize((540, 675), Image.Resampling.LANCZOS)
        sheet.paste(sample, ((cell % 2) * 540, (cell // 2) * 675))
    sheet.save(path, quality=95, subsampling=0)


def write_json_exclusive(path: Path, document: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--font", help="Installed licensed TTF/OTF; no font is copied or redistributed")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--crf", type=int, default=18, choices=range(0, 31))
    parser.add_argument("--preset", default="medium", choices=("ultrafast", "superfast", "veryfast", "faster",
                                                               "fast", "medium", "slow", "slower", "veryslow"))
    parser.add_argument("--validate-only", action="store_true", help="Decode/hash all input PNGs; write nothing")
    parser.add_argument("--preview-only", action="store_true", help="Write stage contact sheets and receipt; no MP4")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt: dict[str, Any] = {"status": "FAILED", "format": "keying-liveaction-reels-v2"}
    receipt_path: Path | None = None
    try:
        cases, identity = load_project(args.manifest)
        font_path = resolve_font(args.font)
        fonts = Fonts(font_path)
        if args.validate_only:
            print(json.dumps({"status": "INPUTS_VALIDATED", **identity, "cases": len(cases),
                              "source_frames_per_case": SOURCE_FRAMES, "source_fps": SOURCE_FPS,
                              "output_fps": FPS, "font": str(font_path),
                              "ground_truth_cases": sum(case.gt is not None for case in cases)}), flush=True)
            return 0
        ffmpeg, ffprobe = shutil.which(args.ffmpeg), shutil.which(args.ffprobe)
        if not ffmpeg or not ffprobe:
            raise RenderError("FFmpeg and FFprobe must be installed or supplied as explicit paths")
        out = args.output_dir.resolve()
        out.mkdir(parents=True, exist_ok=True)
        planned = [out / "render_receipt.json"]
        planned += [out / f"{case.id}_stages.jpg" for case in cases]
        if not args.preview_only:
            planned += [out / combined_name(len(cases)), out / "concat_inputs.txt"]
            planned += [out / f"{case.id}_reel.mp4" for case in cases]
            planned += [out / f"{case.id}_reel.encode.log" for case in cases]
        collisions = [str(p) for p in planned if p.exists()]
        if collisions:
            raise RenderError(f"Refusing to overwrite existing outputs: {collisions}")
        receipt_path = out / "render_receipt.json"
        receipt.update(identity)
        receipt.update({"font": str(font_path), "font_redistributed": False,
                        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "fps": FPS, "source_fps": SOURCE_FPS, "output_size": [WIDTH, HEIGHT],
                        "source_rate_semantics": "Prepared four-second PNG sequence; original acquisition/ingest mapping is in source provenance",
                        "native_size": "per case width/height from manifest",
                        "burned_in_credit": "each case.credit verbatim; no shared source license assumed",
                        "layout": {"header_height": 70, "top_panel_y": TOP_Y, "panel_size": list(PANEL_SIZE),
                                   "gap": 20, "bottom_panel_y": BOTTOM_Y, "footer_y": FOOTER_Y, "footer_height": 44},
                        "clock": {"output_frames_per_case": OUTPUT_FRAMES, "source_frames_per_case": SOURCE_FRAMES,
                                  "mapping": "source_index = (output_index * 24 // 30) % 96; source_time = source_index / 24",
                                  "frame_rate_conversion": "24 to 30 fps by source sample-hold; no synthesized intermediate frames",
                                  "footage_interpolation": False, "output_pts": "output_index / 30",
                                  "stages": [{"output_indices": [0, 119], "view": "full checker composite"},
                                             {"output_indices": [120, 239], "view": "native ROI checker composite"},
                                             {"output_indices": [240, 299], "view": "native ROI model alpha"},
                                             {"output_indices": [300, 359], "view": "native ROI checker composite"}]},
                        "color": {"input": "RGB8 straight sRGB + linear alpha8; assumed input semantic contract",
                                  "composite": "linear-light sRGB; native checker tile chosen for about 27 display pixels in full view, gray sRGB codes 176/208",
                                  "alpha_view": "alpha8 mapped directly to display gray codes",
                                  "display_scaling": "full frame Lanczos; ROI nearest-neighbor; aspect ratio contained",
                                  "encoded": "BT709 matrix/primaries, TV range, sRGB transfer, YUV420p H264",
                                  "filter": COLOR_FILTER, "native_images_changed": False},
                        "audio": False, "intro_outro": False, "cases": [], "videos": []})
        for index, case in enumerate(cases, 1):
            contact = out / f"{case.id}_stages.jpg"
            write_contact_sheet(case, index, len(cases), fonts, contact)
            item = {"id": case.id, "title": case.title, "roi": list(case.roi), "metrics": case.metrics,
                    "native_size": [case.width, case.height], "credit": case.credit,
                    "checker_tile_native_pixels": checker_tile((case.width, case.height)),
                    "ground_truth_available": case.gt is not None,
                    "gt_error_metrics_computed_by_renderer": False,
                    "input_files": case.inputs, "stage_contact_sheet": str(contact)}
            receipt["cases"].append(item)
            if not args.preview_only:
                output = out / f"{case.id}_reel.mp4"
                print(f"Rendering {case.id}: 360 frames / 12 s (96 prepared samples at 24 fps, three loops)", flush=True)
                item["encoder_command"] = encode_case(case, index, len(cases), fonts, output,
                                                       ffmpeg, args.crf, args.preset)
                receipt["videos"].append(verify_video(output, OUTPUT_FRAMES, ffmpeg, ffprobe))
                print(f"Verified {case.id}: clocks, published color tags, all 360 decoded frames", flush=True)
        if not args.preview_only:
            concat_path = out / "concat_inputs.txt"
            with concat_path.open("x", encoding="utf-8", newline="\n") as handle:
                for case in cases:
                    escaped = (out / f"{case.id}_reel.mp4").as_posix().replace("'", "'\\''")
                    handle.write(f"file '{escaped}'\n")
            combined = out / combined_name(len(cases))
            command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n", "-f", "concat",
                       "-safe", "0", "-i", str(concat_path), "-map", "0:v:0", "-an", "-c", "copy",
                       "-video_track_timescale", "30000", "-movflags", "+faststart", str(combined)]
            run_checked(command)
            receipt["combine_command"] = command
            receipt["videos"].append(verify_video(combined, OUTPUT_FRAMES * len(cases), ffmpeg, ffprobe))
        receipt["status"] = ("PREVIEWS_REQUIRING_VISUAL_QA" if args.preview_only
                             else "ENCODED_TECHNICALLY_VERIFIED_REQUIRES_VISUAL_QA")
        write_json_exclusive(receipt_path, receipt)
        print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path),
                          "videos": len(receipt["videos"])}), flush=True)
        return 0
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        if receipt_path is not None and not receipt_path.exists():
            write_json_exclusive(receipt_path, receipt)
        print(receipt["error"], file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
