#!/usr/bin/env python3
"""Two synchronized zoom tiers with symmetric white margins and a two-line creator credit.

Native PNGs/mattes are unchanged. Prepared96@24 samples continue to510@30,
17s/case. All9 final videos receive explicit BT709/TV YUV420p conversion,
BT709 primaries/sRGB transfer tags, full decode and exact packet-clock checks.
No GT accuracy is computed. Attribution is in MP4 artist/comment, never footer.
Checker holds cover frames165..254 (3s) and390..509 (4s). Four comparison
views each dwell30frames/1s; wipes are15frames/.5s. Only viewport/wipe
is held: the source sample clock and original subject/camera motion continue.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import glob
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FPS, SOURCE_FPS, SOURCE_FRAMES, FRAMES = 30, 24, 96, 510
WIPE_FRAMES = 15
BASE_W, BASE_H, TOP, BOTTOM, PANEL_H, FOOTER = 1080, 1350, 56, 686, 608, 1294
CREDIT_LINES = ["Only an LLM + CorridorKey2.0", "See Caption for Details!"]
CREDIT_SIZE, CREDIT_RIGHT, CREDIT_GAP, CREDIT_OPTICAL_DOWN = 20, 27, 3, 1
assert TOP == BASE_H-FOOTER and BOTTOM-(TOP+PANEL_H) == 22
RIGHTS_URL = "https://github.com/hyun2xyz/keying-lab/blob/main/docs/RIGHTS.md"
COLOR_FILTER = (
    "setparams=range=full:color_primaries=bt709:color_trc=iec61966-2-1:colorspace=gbr,"
    "scale=in_color_matrix=bt709:out_color_matrix=bt709:in_range=pc:out_range=tv,"
    "format=yuv420p,setsar=1,"
    "setparams=range=limited:color_primaries=bt709:color_trc=iec61966-2-1:colorspace=bt709"
)
_codes = np.arange(256, dtype=np.float32) / 255
EOTF = np.where(_codes <= .04045, _codes / 12.92, ((_codes + .055) / 1.055) ** 2.4)
CURVES = {"fast_settle": [.20, 0.0, .12, 1.0], "ease_in_out": [.42, 0.0, .58, 1.0]}
CAMERA = [
    [0, 24, 0, 0, "hold"], [24, 60, 0, 1, "fast_settle"],
    [60, 255, 1, 1, "hold"], [255, 285, 1, 2, "fast_settle"],
    [285, 510, 2, 2, "hold"],
]
WIPES = [
    [60, "checker", "source", "left_to_right"],
    [105, "source", "alpha", "right_to_left"],
    [150, "alpha", "checker", "left_to_right"],
    [285, "checker", "black", "right_to_left"],
    [330, "black", "white", "left_to_right"],
    [375, "white", "checker", "right_to_left"],
]
HOLD_RANGES = {"first_checker": [165, 255], "detail_checker": [390, 510]}
VIEW_HOLDS = {"source":[75,105],"alpha":[120,150],"black":[300,330],"white":[345,375]}
CONTACT_FRAMES = [0, 90, 135, 180, 225, 270, 315, 360, 509]


class RenderError(RuntimeError):
    pass


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def source_index(n: int) -> int:
    return (n * SOURCE_FPS // FPS) % SOURCE_FRAMES


def bezier(u: float, controls: list[float]) -> float:
    if u <= 0: return 0.0
    if u >= 1: return 1.0
    x1, y1, x2, y2 = controls
    def b(t: float, a: float, c: float) -> float:
        return 3 * (1-t)**2*t*a + 3*(1-t)*t*t*c + t**3
    lo, hi = 0.0, 1.0
    for _ in range(30):
        t = (lo + hi) * .5
        if b(t, x1, x2) < u: lo = t
        else: hi = t
    return b((lo + hi) * .5, y1, y2)


def camera_progress(n: float) -> float:
    for start, end, before, after, curve in CAMERA:
        if start <= n <= end:
            if before == after: return float(before)
            q = bezier((n-start)/(end-start), CURVES[curve])
            return before + (after-before)*q
    raise RenderError(f"Camera frame out of range: {n}")


def aperture(rect: list[int] | tuple[int, ...], ratio: float) -> tuple[float, float, float]:
    x, y, w, h = rect
    fitted_w = max(w, h*ratio)
    return x+w/2, y+h/2, fitted_w


def viewport(case: "Case", n: float, size: tuple[int, int]) -> tuple[list[float], np.ndarray]:
    ratio = size[0] / size[1]
    stages = [aperture((0,0,case.width,case.height),ratio),aperture(case.roi,ratio),aperture(case.detail_roi,ratio)]
    level = camera_progress(n)
    if level in (0.0,1.0,2.0):
        cx,cy,w = stages[int(level)]
    else:
        index = 0 if level<1 else 1
        q = level-index
        fx,fy,fw = stages[index]
        rx,ry,rw = stages[index+1]
        cx,cy = fx+(rx-fx)*q,fy+(ry-fy)*q
        w = math.exp(math.log(fw)+(math.log(rw)-math.log(fw))*q)
    h = w/ratio
    x, y = cx-w/2, cy-h/2
    sx, sy = w/size[0], h/size[1]
    matrix = np.array([[sx, 0, x+.5*sx-.5], [0, sy, y+.5*sy-.5]], dtype=np.float64)
    return [x, y, w, h], matrix


def wipe_state(n: int, panel_width: int) -> dict:
    current = "checker"
    for start, before, after, direction in WIPES:
        if n < start: break
        if n < start+WIPE_FRAMES:
            u = bezier((n-start+1)/WIPE_FRAMES, CURVES["ease_in_out"])
            seam = round(panel_width*(u if direction == "left_to_right" else 1-u))
            return {"before": before, "after": after, "direction": direction,
                    "progress": u, "seam": seam, "line_visible": 0 < seam < panel_width}
        current = after
    return {"before": current, "after": current, "direction": None,
            "progress": 1.0, "seam": None, "line_visible": False}


@dataclass
class Case:
    id: str
    title: str
    width: int
    height: int
    roi: list[int]
    detail_roi: list[int]
    credit: str
    source_page: str
    source: list[Path]
    pred: list[Path]
    inputs: list[dict]
    alpha_precision: str


def within(root: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or value.drive or ".." in value.parts:
        raise RenderError(f"Expected contained relative path: {relative}")
    path = (root/value).resolve()
    if not path.is_relative_to(root): raise RenderError(f"Escaping path: {relative}")
    return path


def load_cases(path: Path, selected: list[str] | None) -> tuple[list[Case], dict]:
    root, raw = path.resolve().parent, path.read_bytes()
    manifest = json.loads(raw.decode("utf-8-sig"))
    if manifest["fps"] != 24 or manifest.get("output_fps", 30) != 30:
        raise RenderError("Expected prepared24fps sources and30fps output")
    reference_path = within(root, manifest["reference_render_receipt"])
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if sha(reference_path) != manifest["reference_render_receipt_sha256"]:
        raise RenderError("Reference receipt SHA changed")
    prior = {c["id"]: c for c in reference["cases"]}
    cases = []
    requested = set(selected or [c["id"] for c in manifest["cases"]])
    for item in manifest["cases"]:
        if item["id"] not in requested: continue
        if item["id"] == "02_dance" or "/02_dance/" in item["source_dir"].replace("\\", "/"):
            raise RenderError("User-excluded02_dance cannot enter motion output")
        original = prior[item["id"]]
        if (item["roi"] != original["roi"] or [item["width"], item["height"]] != original["native_size"]
                or item["credit"] != original["credit"]):
            raise RenderError(f"Changed approved ROI/dimensions/credit: {item['id']}")
        if item["frames"] != 96 or item["fps"] != 24 or original["ground_truth_available"]:
            raise RenderError("Expected96 prepared samples and no GT")
        if not item.get("source_page", "").startswith("https://"):
            raise RenderError("A source page is required for attribution metadata")
        detail = item.get("detail_roi")
        if (not isinstance(detail,list) or len(detail)!=4
                or any(not isinstance(v,int) or isinstance(v,bool) for v in detail)):
            raise RenderError(f"Missing integer detail_roi: {item['id']}")
        x,y,w,h = detail
        if x<0 or y<0 or w<=0 or h<=0 or x+w>item['width'] or y+h>item['height']:
            raise RenderError(f"Detail ROI outside source: {item['id']}")
        if aperture(detail,1080/608)[2]>=aperture(item['roi'],1080/608)[2]:
            raise RenderError(f"Detail target must be a strictly deeper aspect-fit zoom: {item['id']}")
        source, pred, identities = [], [], []
        for identity in original["input_files"]:
            record = dict(identity)
            for key, expected_key, paths in (("source", "source_sha256", source),
                                              ("prediction", "prediction_sha256", pred)):
                image_path = within(root, identity[key])
                before = image_path.stat()
                if sha(image_path) != identity[expected_key]:
                    raise RenderError(f"PNG SHA differs from fully decoded v1 proof: {image_path}")
                after = image_path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RenderError(f"PNG changed while reading: {image_path}")
                record[key+"_stat"] = [after.st_size, after.st_mtime_ns]
                paths.append(image_path)
            identities.append(record)
        if len(source) != 96 or len(pred) != 96:
            raise RenderError("Reference does not bind96 complete synchronized samples")
        cases.append(Case(item["id"], item["title"], item["width"], item["height"],
                          item["roi"], detail, item["credit"], item["source_page"], source, pred, identities,
                          item["metrics"]["alpha_precision"]))
        print(f"SHA matched v1 native decode proof: {item['id']} (192 PNGs)", flush=True)
    if {c.id for c in cases} != requested: raise RenderError("Unknown requested case")
    return cases, {"manifest": str(path.resolve()), "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                   "reference_render_receipt": str(reference_path), "reference_receipt_sha256": sha(reference_path),
                   "native_png_decode_proof": "Full CRC/sample decode reused from v1; all current source/pred PNG SHA256 matched exactly"}


def resolve_font(value: str | None) -> Path:
    candidates = [Path(value)] if value else []
    if not value:
        candidates += [Path(p) for p in glob.glob("C:/Windows/Fonts/*Jibaek*120*.otf")]
        candidates += [Path(p) for p in glob.glob(str(Path.home()/"AppData/Local/Microsoft/Windows/Fonts/*Jibaek*120*.otf"))]
        candidates += [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        candidates += [Path(p) for p in glob.glob("C:/Program Files/Side Effects Software/*/houdini/fonts/DejaVuSans.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            ImageFont.truetype(str(candidate), 24)
            return candidate.resolve()
    raise RenderError("Supply an installed licensed font with --font")


class Fonts:
    def __init__(self, path: Path, credit_path: Path):
        self.path, self.cache = path, {}
        self.credit_path, self.credit_cache = credit_path, {}
    def get(self, size: int):
        if size not in self.cache: self.cache[size] = ImageFont.truetype(str(self.path), size)
        return self.cache[size]
    def get_credit(self, size: int):
        if size not in self.credit_cache: self.credit_cache[size] = ImageFont.truetype(str(self.credit_path), size)
        return self.credit_cache[size]


def to_srgb(linear: np.ndarray) -> np.ndarray:
    value = np.clip(linear, 0, 1)
    encoded = np.where(value <= .0031308, value*12.92, 1.055*value**(1/2.4)-.055)
    return np.clip(np.rint(encoded*255), 0, 255).astype(np.uint8)


@lru_cache(maxsize=2)
def load_native(source: Path, pred: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with Image.open(source) as im:
        if im.mode != "RGB": raise RenderError("Source must remain RGB8")
        rgb = np.asarray(im, dtype=np.uint8)
    with Image.open(pred) as im:
        if im.mode != "RGBA": raise RenderError("Prediction must remain RGBA8")
        rgba = np.asarray(im, dtype=np.uint8)
    alpha = rgba[..., 3].astype(np.float32)/255
    return EOTF[rgb], EOTF[rgba[..., :3]]*alpha[..., None], alpha


@lru_cache(maxsize=2)
def panel_checker(size: tuple[int, int]) -> np.ndarray:
    yy, xx = np.indices((size[1], size[0]))
    tile = max(1, round(27*size[0]/1080))
    code = np.where(((xx//tile+yy//tile)&1) == 0, 176, 208).astype(np.uint8)
    return np.repeat(EOTF[code][..., None], 3, axis=2)


def white_tag(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
              fonts: Fonts, size: int, scale: float) -> list[int]:
    font, px, py = fonts.get(size), max(3, round(10*scale)), max(2, round(6*scale))
    box = draw.textbbox((0, 0), text, font=font, anchor="lt")
    bounds = [x, y, x+box[2]+2*px, y+box[3]+2*py]
    draw.rectangle(bounds, fill="white")
    draw.text((x+px, y+py), text, font=font, fill="black", anchor="lt")
    return bounds


def credit_geometry(fonts: Fonts, scale: float) -> list[dict]:
    size = round(CREDIT_SIZE*scale)
    font = fonts.get_credit(size)
    right = round((BASE_W-CREDIT_RIGHT)*scale)
    picture_bottom = round(FOOTER*scale)
    last_y = picture_bottom-round(31*scale)+round(CREDIT_OPTICAL_DOWN*scale)
    pitch = round((CREDIT_SIZE+CREDIT_GAP)*scale)
    draw = ImageDraw.Draw(Image.new("RGB",(1,1)))
    result=[]
    for i,text in enumerate(CREDIT_LINES):
        bounds=draw.textbbox((0,0),text,font=font,anchor="lt")
        x=right-bounds[2];y=last_y-(1-i)*pitch
        box=[x-round(3*scale),y-round(2*scale),right+round(3*scale),y+size+round(1*scale)]
        if not (0<=box[0]<box[2]<BASE_W*scale and BOTTOM*scale<box[1]<box[3]<FOOTER*scale):
            raise RenderError("Credit must fit inside lower picture")
        result.append({"text":text,"glyph_xy":[x,y],"box":box,"size":size})
    return result


def draw_creator_credit(draw: ImageDraw.ImageDraw, fonts: Fonts, scale: float) -> list[dict]:
    geometry=credit_geometry(fonts,scale)
    for line in geometry:
        draw.rectangle(line["box"],fill="white")
        draw.text(line["glyph_xy"],line["text"],font=fonts.get_credit(line["size"]),fill="black",anchor="lt")
    return geometry


def frame(case: Case, n: int, fonts: Fonts, output_size: tuple[int, int]) -> tuple[Image.Image, dict]:
    scale = output_size[0]/BASE_W
    size = (output_size[0], round(PANEL_H*scale))
    index = source_index(n)
    source_linear, premult, alpha = load_native(case.source[index], case.pred[index])
    rect, matrix = viewport(case, n, size)
    flags = cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP
    before = cv2.warpAffine(source_linear, matrix, size, flags=flags,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(float(EOTF[224]),)*3)
    rgb = cv2.warpAffine(premult, matrix, size, flags=flags,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    coverage = np.clip(cv2.warpAffine(alpha, matrix, size, flags=flags,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=0), 0, 1)
    rgb = np.minimum(np.maximum(rgb, 0), coverage[..., None])
    source_panel = to_srgb(before)
    state = wipe_state(n, size[0])
    materials = {"source": source_panel}
    def material(name: str) -> np.ndarray:
        if name not in materials:
            if name == "alpha":
                materials[name] = np.repeat(np.rint(coverage*255).astype(np.uint8)[..., None], 3, axis=2)
            else:
                background = panel_checker(size) if name == "checker" else (0 if name == "black" else 1)
                materials[name] = to_srgb(rgb+background*(1-coverage[..., None]))
        return materials[name]
    bottom = material(state["before"]).copy()
    if state["before"] != state["after"]:
        other, seam = material(state["after"]), state["seam"]
        if state["direction"] == "left_to_right": bottom[:, :seam] = other[:, :seam]
        else: bottom[:, seam:] = other[:, seam:]
        if state["line_visible"]:
            black, white = max(1, round(5*scale)), max(1, round(2*scale))
            bottom[:, max(0,seam-black):seam] = 0
            bottom[:, seam:min(size[0],seam+white)] = 255
    image = Image.new("RGB", output_size, "white")
    top_y, bottom_y = round(TOP*scale), round(BOTTOM*scale)
    image.paste(Image.fromarray(source_panel), (0, top_y))
    image.paste(Image.fromarray(bottom), (0, bottom_y))
    draw = ImageDraw.Draw(image)
    boxes = [white_tag(draw, "BEFORE", round(22*scale), top_y+round(17*scale), fonts, round(24*scale), scale)]
    dominant = state["after"] if state["progress"] >= .5 else state["before"]
    lower_label = {"alpha":"ALPHA", "source":"BEFORE"}.get(dominant,"AFTER")
    boxes.append(white_tag(draw, lower_label, round(22*scale),
                           bottom_y+round(17*scale), fonts, round(24*scale), scale))
    credits = draw_creator_credit(draw,fonts,scale)
    footer_y = max(round(FOOTER*scale), bottom_y+size[1])
    gutter_y = top_y+size[1]
    if not np.all(np.asarray(image)[gutter_y:bottom_y] == 255): raise RenderError("Authored gutter is not blank white")
    if top_y != output_size[1]-footer_y: raise RenderError("Outer margins must be exactly symmetric")
    if not np.all(np.asarray(image)[:top_y] == 255): raise RenderError("Authored header is not blank white")
    if not np.all(np.asarray(image)[footer_y:] == 255): raise RenderError("Authored footer is not blank white")
    return image, {"output_index": n, "source_index": index, "source_time": f"{index}/24",
                   "output_pts": f"{n}/30", "camera_progress": camera_progress(n), "viewport_native_xywh": rect,
                   "native_to_display_scale":size[0]/rect[2],
                   "shared_viewport_matrix": matrix.tolist(), "upper_lower_viewport_identical": True,
                   "wipe": state, "authored_text_boxes": boxes, "authored_header_blank":True,
                   "authored_footer_blank": True, "authored_gutter_blank": True, "outer_margins_pixels": [top_y,output_size[1]-footer_y],
                   "authored_credit_lines":credits, "roi_guide_drawn": False}


def metadata(cases: list[Case]) -> dict[str, str]:
    credits = list(dict.fromkeys(c.credit for c in cases))
    lines = [f"{c.id} / {c.title}: {c.credit} | Source: {c.source_page}" for c in cases]
    return {"title":" | ".join(c.title for c in cases),"artist": " ; ".join(credits),
            "comment": "\n".join(lines+[f"Rights: {RIGHTS_URL}",
                         "Edits: synchronized source/keyed comparison, two zoom tiers,3s/4s checker holds,1s comparison-view dwells,15-frame wipes; original source motion continues."])}


def validate_hold_ledger(case: Case, events: list[dict], output_size: tuple[int,int]) -> dict:
    if len(events)!=FRAMES: raise RenderError("Expected510 captured frame events")
    size=(output_size[0],round(PANEL_H*output_size[0]/BASE_W))
    ratio=size[0]/size[1]
    full_w=aperture((0,0,case.width,case.height),ratio)[2]
    first_w=aperture(case.roi,ratio)[2]
    detail_w=aperture(case.detail_roi,ratio)[2]
    for n,event in enumerate(events):
        rect,matrix=viewport(case,n,size)
        if (event['output_index']!=n or event['source_index']!=source_index(n)
                or event['viewport_native_xywh']!=rect or event['shared_viewport_matrix']!=matrix.tolist()
                or event['wipe']!=wipe_state(n,size[0]) or not event['upper_lower_viewport_identical']
                or not event['authored_header_blank'] or not event['authored_footer_blank']
                or len(event['authored_text_boxes'])!=2 or event['roi_guide_drawn']
                or not event['authored_gutter_blank'] or event['outer_margins_pixels']!=[TOP,BASE_H-FOOTER]
                or [x['text'] for x in event['authored_credit_lines']]!=CREDIT_LINES):
            raise RenderError(f"Runtime frame/viewport/wipe contract mismatch at{n}")
    checks={}
    for name,(start,end) in HOLD_RANGES.items():
        samples=events[start:end]
        matrices={tuple(v for row in e['shared_viewport_matrix'] for v in row) for e in samples}
        rects={tuple(e['viewport_native_xywh']) for e in samples}
        source_unique=len({e['source_index'] for e in samples})
        if (len(matrices)!=1 or len(rects)!=1 or source_unique!=(72 if start==165 else 96)
                or any(e['wipe']['before']!='checker' or e['wipe']['after']!='checker'
                       or e['wipe']['line_visible'] for e in samples)):
            raise RenderError(f"Hold drift/wipe/frozen source clock: {case.id}/{name}")
        checks[name]={'output_indices':[start,end-1],'frames':end-start,'seconds':(end-start)/FPS,
                      'viewport_matrix_unique':1,'viewport_rectangle_unique':1,'wipe_active_frames':0,
                      'material':'checker','source_indices_unique':source_unique,'source_clock_continues':True,
                      'raw_rgb_unique':len({e['raw_rgb_sha256'] for e in samples})}
    dwells={}
    for material,(start,end) in VIEW_HOLDS.items():
        samples=events[start:end]
        matrices={tuple(v for row in e['shared_viewport_matrix'] for v in row) for e in samples}
        if (len(samples)!=30 or len(matrices)!=1 or len({e['source_index'] for e in samples})!=24
                or any(e['wipe']['before']!=material or e['wipe']['after']!=material
                       or e['wipe']['line_visible'] for e in samples)):
            raise RenderError(f"Comparison view must dwell1s with continuing source motion: {material}")
        dwells[material]={'output_indices':[start,end-1],'frames':30,'seconds':1,'viewport_matrix_unique':1,
                          'wipe_active_frames':0,'source_indices_unique':24,'source_clock_continues':True,
                          'raw_rgb_unique':len({e['raw_rgb_sha256'] for e in samples})}
    measured=max(size[0]/e['viewport_native_xywh'][2] for e in events)
    expected=size[0]/detail_w
    if not math.isclose(measured,expected,rel_tol=1e-12,abs_tol=1e-12):
        raise RenderError("Maximum detail zoom differs from the selected target")
    if sum(e['wipe']['line_visible'] for e in events)!=84:
        raise RenderError("Expected84 visible boundary samples from6fifteen-frame sweeps")
    return {'holds':checks,'comparison_dwells':dwells,'all510_frame_events_checked':True,'native_detail_scale_expected':expected,
            'native_detail_scale_measured_max':measured,'detail_relative_to_first':first_w/detail_w,
            'detail_relative_to_full':full_w/detail_w,'zoom_overshoot':False,'visible_wipe_boundary_samples':84}


def run(command: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode: raise RenderError(f"Command failed: {command!r}\n{result.stderr[-6000:]}")
    return result


def verify(path: Path, count: int, size: tuple[int,int], tags: dict, ffmpeg: str, ffprobe: str) -> dict:
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_packets", "-show_streams", "-show_format", "-of", "json", str(path)]
    probe = json.loads(run(cmd).stdout)
    stream = probe["streams"][0]
    expected = {"width": size[0], "height": size[1], "codec_name":"h264","profile":"High",
                "pix_fmt": "yuv420p", "sample_aspect_ratio": "1:1",
                "color_range": "tv", "color_space": "bt709", "color_transfer": "iec61966-2-1", "color_primaries": "bt709"}
    for key, value in expected.items():
        if stream.get(key) != value: raise RenderError(f"Published{key}: {stream.get(key)!r}, expected{value!r}")
    if Fraction(stream["time_base"]) != Fraction(1,30000): raise RenderError("Unexpected time base")
    if any(Fraction(stream[key]) != 30 for key in ("r_frame_rate", "avg_frame_rate")): raise RenderError("Unexpected fps")
    packets = probe["packets"]
    if len(packets) != count or int(stream["nb_frames"]) != count: raise RenderError("Wrong sample count")
    for n, packet in enumerate(packets):
        if any(int(packet.get(k,-1)) != v for k,v in (("pts",n*1000),("dts",n*1000),("duration",1000))):
            raise RenderError(f"Unexpected sample clock at{n}: {path}")
    if int(stream["duration_ts"]) != count*1000 or abs(float(probe["format"]["duration"])-count/30)>1e-6:
        raise RenderError("Wrong MP4 sample/container duration")
    actual_tags = probe["format"].get("tags", {})
    for key,value in tags.items():
        if actual_tags.get(key) != value: raise RenderError(f"Attribution metadata mismatch: {key}")
    decode = [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-err_detect", "explode", "-i", str(path),
              "-map", "0:v:0", "-an", "-progress", "pipe:1", "-f", "null", "-"]
    output = run(decode).stdout
    values = re.findall(r"^frame=(\d+)\s*$", output, re.MULTILINE)
    if not values or int(values[-1]) != count: raise RenderError("Full decoder count mismatch")
    header_command=[ffmpeg,"-nostdin","-hide_banner","-v","error","-i",str(path),"-map","0:v:0",
                    "-c:v","copy","-bsf:v","h264_mp4toannexb","-frames:v","1","-f","h264","pipe:1"]
    coded=subprocess.run(header_command,capture_output=True)
    if coded.returncode: raise RenderError("Could not inspect actual H264 encoder headers")
    sei=re.search(rb'x264 - core[^\x00]+',coded.stdout)
    parameters=sei.group().decode('ascii',errors='replace') if sei else ''
    if not re.search(r'\bcrf=10\.0(?:\s|$)',parameters):
        raise RenderError("Actual x264 SEI does not confirm CRF10")
    return {"path":str(path),"sha256":sha(path),"bytes":path.stat().st_size,"frames":count,"seconds":count/30,
            "full_decode_frames":count,"time_base":"1/30000","all_packet_pts_dts_durations_checked":True,
            "published_color":expected,"attribution_metadata":tags,"probe_command":cmd,"decode_command":decode,
            "actual_x264_sei":parameters,"actual_crf_confirmed":10,"header_command":header_command,
            "preset_from_encoding_invocation":"slow"}


def encode(case: Case, fonts: Fonts, out: Path, size: tuple[int,int], args) -> dict:
    target = out/(case.id+"_reel.mp4")
    tags = metadata([case])
    command = [args.ffmpeg,"-nostdin","-hide_banner","-v","error","-n","-f","rawvideo","-pixel_format","rgb24",
               "-video_size",f"{size[0]}x{size[1]}","-framerate","30","-i","pipe:0","-map","0:v:0","-an","-vf",COLOR_FILTER,
               "-c:v","libx264","-preset",args.preset,"-crf",str(args.crf),"-profile:v","high","-bf","0","-pix_fmt","yuv420p",
               "-fps_mode","passthrough","-frames:v",str(FRAMES),"-color_range","tv","-colorspace","bt709","-color_primaries","bt709",
               "-color_trc","iec61966-2-1","-video_track_timescale","30000","-movflags","+faststart+use_metadata_tags"]
    for k,v in tags.items(): command += ["-metadata",f"{k}={v}"]
    command += [str(target)]
    ledger_path = out/(case.id+"_frames.jsonl")
    with (out/(case.id+"_encode.log")).open("xb") as log, ledger_path.open("x",encoding="utf-8",newline="\n") as ledger:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            for n in range(FRAMES):
                im, event = frame(case,n,fonts,size)
                raw = im.tobytes()
                process.stdin.write(raw)
                event["raw_rgb_sha256"] = hashlib.sha256(raw).hexdigest()
                ledger.write(json.dumps(event,separators=(",",":"))+"\n")
                if n%30 == 29: ledger.flush()
                if n in (75,120,165,255,285,300,345,390,509):
                    print(f"{case.id} frame{n}/509 submitted; viewport level{event['camera_progress']:.3f}",flush=True)
            process.stdin.close()
            code = process.wait()
        except BaseException:
            process.terminate(); process.wait()
            raise
    if code: raise RenderError(f"Encoder failed; preserved{target} and log")
    events=[json.loads(line) for line in ledger_path.read_text(encoding='utf-8').splitlines()]
    hold_validation=validate_hold_ledger(case,events,size)
    proof = verify(target,FRAMES,size,tags,args.ffmpeg,args.ffprobe)
    proof.update({"encoder_command":command,"runtime_frame_ledger":str(ledger_path),"ledger_sha256":sha(ledger_path),
                  "hold_validation":hold_validation})
    with (out/(case.id+"_technical.json")).open("x",encoding="utf-8") as handle: json.dump(proof,handle,indent=2)
    return proof


def contact(case: Case, fonts: Fonts, out: Path) -> str:
    sheet = Image.new("RGB",(1080,1350),"white")
    stills=out/"stills";stills.mkdir(exist_ok=True)
    for cell,n in enumerate(CONTACT_FRAMES):
        im,_ = frame(case,n,fonts,(1080,1350))
        if n in (0,509):
            target=stills/(f"{case.id}_frame{n:03d}_full1080.png")
            if target.exists(): raise RenderError("Existing full1080 still; do not overwrite")
            im.save(target)
        sheet.paste(im.resize((360,450),Image.Resampling.LANCZOS),((cell%3)*360,(cell//3)*450))
    path = out/(case.id+"_caption_contact.jpg")
    if path.exists(): raise RenderError(f"Refusing overwrite: {path}")
    sheet.save(path,quality=95,subsampling=0)
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--cases",nargs="+")
    parser.add_argument("--output-size",default="1080x1350")
    parser.add_argument("--font")
    parser.add_argument("--credit-font",required=True,help="Licensed local Jibaek120 font matching the accepted breakdown reference; not redistributed")
    parser.add_argument("--ffmpeg",default="ffmpeg")
    parser.add_argument("--ffprobe",default="ffprobe")
    parser.add_argument("--preset",default="slow")
    parser.add_argument("--crf",type=int,default=10)
    parser.add_argument("--preview-only",action="store_true")
    parser.add_argument("--no-combined",action="store_true")
    args = parser.parse_args()
    size = tuple(map(int,args.output_size.lower().split("x")))
    if len(size)!=2 or any(v<2 or v%2 for v in size) or size[0]*1350!=size[1]*1080:
        raise RenderError("Output must be even dimensions with1080:1350 aspect, e.g720x900")
    if size!=(1080,1350) or args.preset!='slow' or args.crf!=10:
        raise RenderError("Caption v6 requires native-PNG1080x1350 delivery with CRF10/preset slow")
    for key in ("ffmpeg","ffprobe"):
        found = shutil.which(getattr(args,key))
        if not found: raise RenderError(f"Missing{key}")
        setattr(args,key,found)
    cv2.setNumThreads(2)
    cases, identity = load_cases(args.manifest,args.cases)
    font_path = resolve_font(args.font)
    credit_path = resolve_font(args.credit_font)
    fonts = Fonts(font_path,credit_path)
    out = args.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    if (out/"caption_receipt.json").exists(): raise RenderError("Existing motion receipt; use a new directory")
    for case in cases:
        if (out/(case.id+"_reel.mp4")).exists(): raise RenderError("Existing MP4; use a new directory")
    receipt = {"status":"FAILED",**identity,"output_size":list(size),"fps":30,"case_frames":FRAMES,"case_seconds":FRAMES/FPS,
               "font":{"path":str(font_path),"sha256":sha(font_path),"family":fonts.get(24).getname(),"redistributed":False},
               "credit_font":{"path":str(credit_path),"sha256":sha(credit_path),"family":fonts.get_credit(CREDIT_SIZE).getname(),"redistributed":False},
               "renderer_sha256":sha(Path(__file__)),"opencv_version":cv2.__version__,
               "encoding_quality":{"codec":"libx264","profile":"high","pixel_format":"yuv420p","crf":10,"preset":"slow",
                                   "direct_native_png_input":True,"reencoded_from_pilot":False},
               "layout":{"canvas":[1080,1350],"top_panel":[0,56,1080,608],"bottom_panel":[0,686,1080,608],
                         "white_canvas":True,"roi_guides":False,"bottom_text":False,"main_title":False,
                         "header_blank_white_pixels":56,"footer_blank_white_pixels":56,"gutter_blank_white_pixels":22,"symmetric_outer_margins":True,
                         "creator_credit":{"lines":CREDIT_LINES,"size":CREDIT_SIZE,"right_glyph_margin":CREDIT_RIGHT,"line_gap":CREDIT_GAP,"optical_downshift":CREDIT_OPTICAL_DOWN,"geometry":credit_geometry(fonts,1.0),"inside_lower_picture":True},
                         "text":"BEFORE/AFTER/ALPHA at panel upper-left plus user-requested two-line creator credit at lower-picture bottom-right, white text-width boxes and black glyphs. Outer margins and gutter remain blank white."},
               "camera":{"segments":CAMERA,"bezier_curves":CURVES,"stage_levels":{"0":"full","1":"first ROI","2":"detail ROI"},
                         "interpolation":"Continuous center/log aperture; zero endpoint velocity; exact constant viewport in holds",
                         "checker_holds":{"first":[165,254],"detail":[390,509]},"hold_seconds":[3,4],"source_motion_continues":True},
               "wipes":{"events":WIPES,"samples_each":WIPE_FRAMES,"seconds_each":WIPE_FRAMES/FPS,
                        "comparison_dwells":VIEW_HOLDS,"dwell_seconds":1,"line_at1080":"5px black left +2px white right","both_sides_clock":"same advancing source frame and identical viewport"},
               "clock":{"source_index":"(n*24//30)%96","output_pts":"n/30","temporal_interpolation":False,"source_loops":FRAMES*SOURCE_FPS/FPS/SOURCE_FRAMES},
               "color":{"source":"declared sRGB RGB8; linear alpha8","resampling":"float32 linear-light premultiplied RGB+alpha, shared cubic spatial viewport; coverage clipped0..1",
                        "checker":"screen-space gray176/208,27px tiles at1080","alpha":"coverage maps directly to gray display code",
                        "encoding_filter":COLOR_FILTER},
               "rights":{"onscreen_source_credit":False,"onscreen_creator_credit":True,"external_rights":RIGHTS_URL,"mp4_metadata":"artist + comment include every case credit/sourcepage"},
               "cutout_precision":"Original prediction PNGs unchanged; native ProRes alpha10-effective/16-bit storage proof reused, RGBA8 presentation; no new inference",
               "ground_truth_available":False,"accuracy_metrics_computed":False,"audio":False,"cases":[],"videos":[]}
    try:
        for case in cases:
            item={"id":case.id,"title":case.title,"native_size":[case.width,case.height],"roi":case.roi,"detail_roi":case.detail_roi,
                  "credit":case.credit,"source_page":case.source_page,"input_files":case.inputs,"alpha_precision":case.alpha_precision}
            if args.preview_only:
                item["contact"] = contact(case,fonts,out)
                item["full1080_stills"]=[str(out/'stills'/f'{case.id}_frame{n:03d}_full1080.png') for n in (0,509)]
            else:
                print(f"Rendering caption HQ: {case.id} ({FRAMES} frames)",flush=True)
                receipt["videos"].append(encode(case,fonts,out,size,args))
                print(f"Verified caption HQ: {case.id} full decode/color/clock/metadata",flush=True)
            receipt["cases"].append(item)
            load_native.cache_clear()
        if not args.preview_only and not args.no_combined:
            listing=out/"concat_inputs.txt"
            with listing.open("x",encoding="utf-8",newline="\n") as handle:
                for case in cases:
                    escaped=(out/(case.id+"_reel.mp4")).as_posix().replace("'","'\\''")
                    handle.write(f"file '{escaped}'\n")
            target=out/(f"keying_breakdown_real{len(cases)}_1080x1350.mp4")
            tags=metadata(cases)
            command=[args.ffmpeg,"-nostdin","-hide_banner","-v","error","-n","-f","concat","-safe","0","-i",str(listing),
                     "-map","0:v:0","-an","-c","copy","-map_metadata","-1","-video_track_timescale","30000","-movflags","+faststart+use_metadata_tags"]
            for k,v in tags.items(): command += ["-metadata",f"{k}={v}"]
            command += [str(target)]
            run(command)
            receipt["combine_command"]=command
            receipt["videos"].append(verify(target,FRAMES*len(cases),size,tags,args.ffmpeg,args.ffprobe))
        receipt["status"]="PREVIEWS_REQUIRE_DIRECT_REVIEW" if args.preview_only else "ENCODED_TECHNICALLY_VERIFIED_REQUIRES_VISUAL_QA"
    except Exception as exc:
        receipt["error"]=f"{type(exc).__name__}: {exc}"
        raise
    finally:
        with (out/"caption_receipt.json").open("x",encoding="utf-8",newline="\n") as handle:
            json.dump(receipt,handle,ensure_ascii=False,indent=2,allow_nan=False); handle.write("\n")
    print(json.dumps({"status":receipt["status"],"receipt":str(out/"caption_receipt.json"),"videos":len(receipt["videos"])}),flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
