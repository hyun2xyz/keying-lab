"""Reuse five completed CorridorKey movies; never run a model or fetch media.

Source PNG code values and the legacy review's FFmpeg default movie decoding
are the reference.  The explicit 709/limited decoder must reproduce that
default on actual selected frames.  This is not a physical camera-color claim.
All outputs are new, local-only, square-pixel caches and separate evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, PngImagePlugin, __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[3]
LAB = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/caption_v6_20261029'
SOURCE_PAGE = 'https://www.hollywoodcamerawork.com/green-screen-plates.html'
DECODE_FILTER = 'scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgba64le'
cv2.setNumThreads(2)

CASES = [
    dict(id='09_legacy_hair', name='hair_detail', title='Hair detail',
         source='work/inputs/hair_detail', movie='outputs/hair_detail/hair_detail_cutout.mov',
         stored_size=[1280, 1080], size=[1920, 1080], source_fps=30, native_frames=80,
         frames=64, par='3:2', roi=[480, 60, 960, 540], detail_roi=[720, 80, 480, 270]),
    dict(id='10_legacy_motion_blur', name='motion_blur', title='Motion blur',
         source='work/inputs/motion_blur', movie='outputs/motion_blur/motion_blur_cutout.mov',
         stored_size=[1280, 1080], size=[1920, 1080], source_fps=30, native_frames=50,
         frames=40, par='3:2', roi=[240, 120, 1280, 720], detail_roi=[360, 200, 640, 360]),
    dict(id='11_legacy_metal_glasses', name='metal_glasses', title='Metal glasses',
         source='work/more3/inputs/metal_glasses', movie='outputs/more3/metal_glasses/metal_glasses_cutout.mov',
         stored_size=[1280, 1080], size=[1920, 1080], source_fps=30, native_frames=90,
         frames=72, par='3:2', roi=[480, 60, 960, 540], detail_roi=[720, 120, 480, 270]),
    dict(id='12_legacy_smoke', name='smoke', title='Smoke',
         source='work/more3/inputs/smoke', movie='outputs/more3/smoke/smoke_cutout.mov',
         stored_size=[1280, 1080], size=[1920, 1080], source_fps=30, native_frames=120,
         frames=96, par='3:2', roi=[480, 120, 960, 540], detail_roi=[720, 220, 480, 270]),
    dict(id='13_legacy_fullbody', name='uneven_fullbody', title='Uneven screen / full body',
         source='work/more3/inputs/uneven_fullbody', movie='outputs/more3/uneven_fullbody/uneven_fullbody_cutout.mov',
         stored_size=[960, 720], size=[1280, 720], source_fps=60, native_frames=180,
         frames=72, par='4:3', roi=[240, 30, 800, 450], detail_roi=[400, 80, 400, 225]),
]

UPSTREAM_FILES = [
    'work/make_review.py', 'work/more3/run_batch.py', 'work/run_test.py',
    'work/more3/infer_one.py', 'work/input-info.json', 'work/more3/parameters.json',
    'work/samples-ready.json', 'work/more3/download-ready.json',
    'work/CorridorKey2.0/corridorkey/video_io.py',
    'work/CorridorKey2.0/corridorkey/runtime.py',
]


def log(*parts):
    print(datetime.now().astimezone().isoformat(timespec='seconds'), *parts, flush=True)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def rel(path, root=ROOT):
    return Path(path).resolve().relative_to(root.resolve()).as_posix()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def identity(path):
    path = Path(path)
    stat = path.stat()
    return dict(path=rel(path), bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=sha(path))


def png_header(path):
    with Path(path).open('rb') as f:
        header = f.read(33)
    if header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        raise ValueError(f'Not a PNG: {path}')
    w, h, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', header[16:29])
    return dict(width=w, height=h, bit_depth=depth, color_type=color, interlace=interlace)


def small_info(path):
    with Image.open(path) as im:
        info = {}
        for key, value in im.info.items():
            if isinstance(value, bytes):
                info[key] = dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
            elif isinstance(value, str) and len(value) > 300:
                info[key] = dict(characters=len(value), sha256_utf8=hashlib.sha256(value.encode('utf-8')).hexdigest())
            else:
                info[key] = value
        return dict(mode=im.mode, size=list(im.size), metadata=info)


def probe(path, packets=False):
    args = ['ffprobe', '-v', 'error', '-select_streams', 'v:0']
    if packets:
        args += ['-show_packets', '-show_entries', 'packet=pts,dts,duration,size,flags']
    else:
        args += ['-show_streams', '-show_format']
    return json.loads(subprocess.check_output(args + ['-of', 'json', str(path)], text=True, encoding='utf-8'))


def original_files():
    files = [ROOT / p for p in UPSTREAM_FILES]
    for c in CASES:
        movie = ROOT / c['movie']
        files.extend([movie, movie.with_name(c['name'] + '_settings.txt')])
        files.extend(sorted((ROOT / c['source']).glob('*.png')))
    return files


def freeze_inputs(path):
    if Path(path).exists():
        raise FileExistsError(path)
    cases = []
    for c in CASES:
        sources = sorted((ROOT / c['source']).glob('*.png'))
        if len(sources) != c['native_frames'] or [p.name for p in sources] != [f'{i:05}.png' for i in range(c['native_frames'])]:
            raise ValueError(f'Original source count/names changed: {c["id"]}')
        for p in sources:
            hdr = png_header(p)
            if [hdr['width'], hdr['height']] != c['stored_size'] or hdr['bit_depth'] != 8 or hdr['color_type'] != 2:
                raise ValueError(f'Unexpected original PNG contract: {p}: {hdr}')
        movie_probe = probe(ROOT / c['movie'])
        stream = movie_probe['streams'][0]
        if [stream['width'], stream['height']] != c['stored_size'] or int(stream['nb_frames']) != c['native_frames']:
            raise ValueError(f'Original movie size/count mismatch: {c["id"]}')
        if Fraction(stream['avg_frame_rate']) != c['source_fps'] or stream['codec_name'] != 'prores':
            raise ValueError(f'Original movie clock/codec mismatch: {c["id"]}')
        settings_path = ROOT / c['movie']
        settings = settings_path.with_name(c['name'] + '_settings.txt').read_text(encoding='utf-8-sig')
        if 'Cutout Linear: False' not in settings or 'Frame Dir Linear: False' not in settings:
            raise ValueError(f'Need separately reviewed transfer convention: {c["id"]}')
        if Fraction(c['native_frames'], c['source_fps']) != Fraction(c['frames'], 24):
            raise ValueError('Prepared count would change excerpt duration')
        cases.append(dict(**c, original_movie_probe=movie_probe,
            source_png_selected_metadata=[dict(frame=i, **small_info(sources[i]))
                for i in [0, len(sources)//2, len(sources)-1]]))
    rows = []
    for p in original_files():
        rows.append(identity(p))
    result = dict(schema_version=1, status='FROZEN_EXISTING_INPUTS', created_utc=datetime.now(timezone.utc).isoformat(),
        purpose='Reuse existing legacy model movies only; no new inference, download or source modification.',
        cases=cases, files=rows, preparer=identity(__file__))
    write_new_json(path, result)
    log('FROZEN', len(rows), 'existing files', rel(path))


def verify_frozen(frozen):
    for row in frozen['files']:
        p = ROOT / row['path']
        if not p.is_file() or p.stat().st_size != row['bytes'] or sha(p) != row['sha256']:
            raise ValueError(f'Frozen original changed: {row["path"]}')
    if sha(__file__) != frozen['preparer']['sha256']:
        raise ValueError('Prepared script changed after input freeze')
    return dict(files=len(frozen['files']), full_sha256_recomputed=True, unchanged=True)


def eotf(x):
    x = np.asarray(x, dtype=np.float32)
    return np.where(x <= .04045, x / 12.92, ((x + .055) / 1.055) ** 2.4)


def oetf(x):
    x = np.maximum(x, 0)
    return np.where(x <= .0031308, x * 12.92, 1.055 * x ** (1/2.4) - .055)


def quant8(x):
    return np.rint(np.clip(x, 0, 1) * 255).astype(np.uint8)


def resize_source(rgb, size):
    return quant8(oetf(cv2.resize(eotf(rgb.astype(np.float32) / 255), tuple(size), interpolation=cv2.INTER_LANCZOS4)))


def resize_prediction(rgba16, size):
    rgba = rgba16.astype(np.float32) / 65535
    a = rgba[..., 3]
    lin = eotf(rgba[..., :3])
    a_out_unclipped = cv2.resize(a, tuple(size), interpolation=cv2.INTER_LANCZOS4)
    a_out = np.clip(a_out_unclipped, 0, 1)
    premul_raw = cv2.resize(lin * a[..., None], tuple(size), interpolation=cv2.INTER_LANCZOS4)
    premul = np.minimum(np.maximum(premul_raw, 0), a_out[..., None])
    rgb_out = np.divide(premul, a_out[..., None], out=np.zeros_like(premul), where=a_out[..., None] > 1e-7)
    a8 = quant8(a_out)
    rgb8 = quant8(oetf(rgb_out))
    rgb8[a8 == 0] = 0
    result = np.dstack([rgb8, a8])
    diagnostics = dict(coverage_clip_low_samples=int((a_out_unclipped < 0).sum()),
        coverage_clip_high_samples=int((a_out_unclipped > 1).sum()),
        premultiplied_rgb_clip_samples=int(((premul_raw < 0) | (premul_raw > a_out[..., None])).sum()))
    return result, diagnostics


def save_png(path, array):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    info = PngImagePlugin.PngInfo()
    info.add(b'sRGB', b'\x00')
    Image.fromarray(array).save(path, pnginfo=info, compress_level=3)
    expected_type = 2 if array.shape[2] == 3 else 6
    header = png_header(path)
    if header['bit_depth'] != 8 or header['color_type'] != expected_type:
        raise ValueError(f'Wrong prepared PNG IHDR: {path}')
    with Image.open(path) as im:
        actual = np.asarray(im)
        if not np.array_equal(actual, array):
            raise ValueError(f'Prepared PNG readback mismatch: {path}')
    return dict(path=rel(path, LAB), sha256=sha(path), bytes=path.stat().st_size,
                decoded_pixels_sha256=hashlib.sha256(array.tobytes()).hexdigest(), ihdr=header)


def read_exact(pipe, count):
    data = bytearray()
    while len(data) < count:
        block = pipe.read(count - len(data))
        if not block:
            break
        data.extend(block)
    return bytes(data)


def selected_decode(movie, indices, explicit, depth):
    select = 'select=' + '+'.join(f'eq(n\\,{i})' for i in indices)
    if explicit:
        select += ',' + DECODE_FILTER.replace('rgba64le', 'rgba64le' if depth == 16 else 'rgba')
    pix = 'rgba64le' if depth == 16 else 'rgba'
    command = ['ffmpeg', '-v', 'error', '-xerror', '-threads', '2', '-i', str(movie), '-map', '0:v:0',
        '-vf', select, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', pix, '-']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, check=True)
    return result.stdout, command


def compare_default(c):
    movie = ROOT / c['movie']
    indices = [0, c['native_frames']//2, c['native_frames']-1]
    rows = []
    for depth in [8, 16]:
        default, default_command = selected_decode(movie, indices, False, depth)
        explicit, explicit_command = selected_decode(movie, indices, True, depth)
        frame_bytes = int(np.prod(c['stored_size'])) * 4 * (depth//8)
        if len(default) != frame_bytes * len(indices) or len(explicit) != len(default):
            raise ValueError(f'Selected decode truncated: {c["id"]}')
        if default != explicit:
            a = np.frombuffer(default, np.uint8 if depth == 8 else '<u2').astype(np.int32)
            b = np.frombuffer(explicit, np.uint8 if depth == 8 else '<u2').astype(np.int32)
            raise ValueError(f'Default/explicit decode differs: {c["id"]}, {depth}bit, max={np.abs(a-b).max()}')
        per_frame = []
        for k, i in enumerate(indices):
            per_frame.append(dict(original_index=i, default_sha256=hashlib.sha256(default[k*frame_bytes:(k+1)*frame_bytes]).hexdigest(),
                explicit_sha256=hashlib.sha256(explicit[k*frame_bytes:(k+1)*frame_bytes]).hexdigest(), rgb_max_difference=0, alpha_max_difference=0))
        rows.append(dict(storage_bits=depth, byte_identical=True, frames=per_frame, default_command=default_command,
                         explicit_command=explicit_command, interpretation='Playback-default reproduction, not proof of physical encoding matrix.'))
    return dict(status='PASS', original_indices=indices, comparisons=rows)


def resampling_control():
    # Hidden colors at alpha=0 must not leak through PAR interpolation.
    a = np.zeros((16, 24, 4), np.uint16)
    a[..., 0] = 65535
    a[:, 12:, :3] = [0, 0, 65535]
    a[:, 12:, 3] = 65535
    b = a.copy()
    b[:, :12, :3] = [0, 65535, 0]
    out_a, _ = resize_prediction(a, [36, 16])
    out_b, _ = resize_prediction(b, [36, 16])
    if not np.array_equal(out_a, out_b):
        raise ValueError('Hidden RGB leaked through premultiplied interpolation')
    # Linear-light resizing must differ from gamma-code interpolation on a contrast edge.
    ramp = np.zeros((16, 24, 3), np.uint8)
    ramp[:, 12:] = 255
    source = resize_source(ramp, [36, 16])
    code_resize = cv2.resize(ramp, (36, 16), interpolation=cv2.INTER_LANCZOS4)
    delta = int(np.abs(source.astype(np.int16) - code_resize.astype(np.int16)).max())
    if delta <= 0:
        raise ValueError('Linear-light control did not discriminate gamma-code resizing')
    return dict(status='PASS', synthetic_control_only=True, hidden_transparent_rgb_max_difference=0,
        linear_vs_code_interpolation_max_code_difference=delta, temporal_interpolation=False)


def check_packet_clock(c, movie_probe):
    packets = probe(ROOT / c['movie'], packets=True)['packets']
    stream = movie_probe['streams'][0]
    tb = Fraction(stream['time_base'])
    if len(packets) != c['native_frames']:
        raise ValueError(f'Original packet count mismatch: {c["id"]}')
    for i, p in enumerate(packets):
        if Fraction(int(p['pts'])) * tb != Fraction(i, c['source_fps']):
            raise ValueError(f'Original PTS mismatch: {c["id"]}/{i}')
        if Fraction(int(p['duration'])) * tb != Fraction(1, c['source_fps']):
            raise ValueError(f'Original sample duration mismatch: {c["id"]}/{i}')
    return dict(status='PASS', time_base=stream['time_base'], frames=len(packets),
        first_pts=packets[0]['pts'], final_pts=packets[-1]['pts'],
        duration_seconds=str(Fraction(c['native_frames'], c['source_fps'])), packets=packets)


def composite_checker(rgba):
    h, w = rgba.shape[:2]
    yy, xx = np.indices((h, w))
    checker = np.where(((xx//48 + yy//48) % 2)[..., None], 208/255, 176/255).astype(np.float32)
    alpha = rgba[..., 3:4].astype(np.float32)/255
    return quant8(oetf(eotf(rgba[..., :3].astype(np.float32)/255)*alpha + eotf(checker)*(1-alpha)))


def contacts(c, source_dir, pred_dir):
    indices = [0, c['frames']//2, c['frames']-1]
    tile = (640, 360)
    sheet = Image.new('RGB', (3*tile[0], 3*(tile[1]+28)), 'white')
    draw = ImageDraw.Draw(sheet)
    native_selected = []
    for col, i in enumerate(indices):
        s_path = source_dir / f'{i:05}.png'
        p_path = pred_dir / f'{i:05}.png'
        with Image.open(s_path) as im:
            src = np.asarray(im)
        with Image.open(p_path) as im:
            pred = np.asarray(im)
        alpha = np.repeat(pred[..., 3:4], 3, axis=2)
        comp = composite_checker(pred)
        alpha_path = WORK / f'legacy_{c["id"]}_alpha_{i:05}.png'
        comp_path = WORK / f'legacy_{c["id"]}_checker_{i:05}.png'
        Image.fromarray(alpha).save(alpha_path, compress_level=3)
        Image.fromarray(comp).save(comp_path, compress_level=3)
        native_selected.append(dict(prepared_index=i, original_index=i*c['source_fps']//24,
            source=rel(s_path), prediction=rel(p_path), alpha=rel(alpha_path), checker=rel(comp_path)))
        for row, (label, array) in enumerate([('SOURCE', src), ('MODEL ALPHA', alpha), ('CHECKER', comp)]):
            x, y = col*tile[0], row*(tile[1]+28)
            draw.text((x+8, y+5), f'{c["id"]} | {label} | prepared {i}, original {i*c["source_fps"]//24}', fill='black')
            sheet.paste(Image.fromarray(array).resize(tile, Image.Resampling.LANCZOS), (x, y+28))
    path = WORK / f'legacy_{c["id"]}_source_alpha_checker_contact.jpg'
    sheet.save(path, quality=96, subsampling=0)
    return dict(contact=identity(path), native_selected=native_selected,
        contact_is_reduced_review_aid=True, native_cache_files_are_full_display_resolution=True)


def prepare_case(c, frozen_by_path):
    started = time.perf_counter()
    case_root = LAB / 'results' / c['id']
    case_root.mkdir(parents=False, exist_ok=False)
    source_dir = case_root / 'source_reuse'
    pred_dir = case_root / 'pred_rgba'
    source_dir.mkdir()
    pred_dir.mkdir()
    color_compare = compare_default(c)
    movie_probe = probe(ROOT / c['movie'])
    clock = check_packet_clock(c, movie_probe)
    mapping = {j*c['source_fps']//24: j for j in range(c['frames'])}
    input_files, frame_mapping, decoded_ledger = [], [], []
    whole_decoded_hash = hashlib.sha256()
    hist_alpha = np.zeros(65536, dtype=np.int64)
    movie = ROOT / c['movie']
    w, h = c['stored_size']
    frame_bytes = w*h*8
    command = ['ffmpeg', '-v', 'error', '-xerror', '-threads', '2', '-i', str(movie), '-map', '0:v:0',
        '-vf', DECODE_FILTER, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgba64le', '-']
    stderr_path = WORK / f'legacy_{c["id"]}_full_decode.stderr.log'
    decode_count = 0
    with stderr_path.open('xb') as err:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL)
        try:
            for i in range(c['native_frames']):
                data = read_exact(proc.stdout, frame_bytes)
                if len(data) != frame_bytes:
                    raise ValueError(f'Truncated original cutout: {c["id"]}/{i}: {len(data)}')
                decode_count += 1
                frame_sha = hashlib.sha256(data).hexdigest()
                whole_decoded_hash.update(data)
                rgba16 = np.frombuffer(data, '<u2').reshape(h, w, 4)
                hist_alpha += np.bincount(rgba16[..., 3].ravel(), minlength=65536)
                decoded_ledger.append(dict(original_index=i, pts=clock['packets'][i]['pts'], rgba64le_sha256=frame_sha))
                if i in mapping:
                    j = mapping[i]
                    old_source = ROOT / c['source'] / f'{i:05}.png'
                    with Image.open(old_source) as im:
                        im.load()
                        if im.mode != 'RGB' or list(im.size) != c['stored_size']:
                            raise ValueError(f'Selected source contract changed: {old_source}')
                        source = np.asarray(im)
                    source8 = resize_source(source, c['size'])
                    pred8, diagnostics = resize_prediction(rgba16, c['size'])
                    s = save_png(source_dir / f'{j:05}.png', source8)
                    p = save_png(pred_dir / f'{j:05}.png', pred8)
                    input_files.append(dict(stem=f'{j:05}', source=s['path'], source_sha256=s['sha256'],
                        prediction=p['path'], prediction_sha256=p['sha256']))
                    frame_mapping.append(dict(prepared_index=j, prepared_time_seconds=str(Fraction(j, 24)),
                        original_index=i, original_time_seconds=str(Fraction(i, c['source_fps'])),
                        held_sample_age_seconds=str(Fraction(j,24)-Fraction(i,c['source_fps'])),
                        original_source=frozen_by_path[rel(old_source)], original_movie_frame_rgba64le_sha256=frame_sha,
                        source_cache=s, prediction_cache=p, resampling=diagnostics))
                    if j % 12 == 0 or j == c['frames']-1:
                        log('CACHE', c['id'], f'{j+1}/{c["frames"]}', 'original', i)
            if proc.stdout.read(1):
                raise ValueError(f'Extra original cutout frames: {c["id"]}')
            proc.stdout.close()
            returncode = proc.wait(timeout=120)
            if returncode:
                raise ValueError(f'Original cutout full decode failed: {c["id"]}, rc={returncode}')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=30)
    if len(input_files) != c['frames'] or decode_count != c['native_frames']:
        raise ValueError(f'Prepared/full decode count mismatch: {c["id"]}')
    # Actual selected full-decode frames must also match the independent default comparison.
    default16 = next(x for x in color_compare['comparisons'] if x['storage_bits'] == 16)
    for row in default16['frames']:
        if decoded_ledger[row['original_index']]['rgba64le_sha256'] != row['default_sha256']:
            raise ValueError('Full decode does not reproduce independent selected default decode')
    proof = dict(status='PASS', proof_kind='LEGACY_PRIOR_MOVIE_FULL_DECODE',
        not_from_native_v1_receipt=True, original_movie=frozen_by_path[c['movie']],
        original_stream=movie_probe, packet_clock=clock, command=command,
        expected_frames=c['native_frames'], decoded_frames=decode_count, decoder_exit_code=returncode,
        eof_after_expected_last_frame=True, bytes_decoded=decode_count*frame_bytes,
        concatenated_decoded_rgba64le_sha256=whole_decoded_hash.hexdigest(),
        frame_ledger=decoded_ledger, decode_stderr=rel(stderr_path),
        decode_stderr_bytes=stderr_path.stat().st_size, default_decode_comparison=color_compare,
        original_alpha16_storage_distinct_codes=int(np.count_nonzero(hist_alpha)),
        precision='Upstream bgra64le uint16 -> yuva444p10le -> ProRes4444 decoded yuva444p12le -> RGBA16 storage. Effective alpha is bounded by upstream10bit quantization, not16bit accuracy. Prepared cache is RGB8 + linear alpha8.',
        matrix_interpretation='Explicit709/TV reproduces this FFmpeg default decoder at actual0/mid/last frames, in bothRGBA8 andRGBA16. Writer declared709 but used automatic RGB-to-YUV conversion; this does not prove camera primaries, transfer or physically correct encoding matrix.')
    proof_path = WORK / f'legacy_{c["id"]}_movie_decode.json'
    write_new_json(proof_path, proof)
    review = contacts(c, source_dir, pred_dir)
    stream = movie_probe['streams'][0]
    tag_fields = ['color_space', 'color_range', 'color_primaries', 'color_transfer', 'sample_aspect_ratio']
    result = dict(id=c['id'], title=c['title'], width=c['size'][0], height=c['size'][1],
        frames=c['frames'], fps=24, source_fps=24, source_dir=rel(source_dir, LAB), pred_rgba_dir=rel(pred_dir, LAB),
        roi=c['roi'], detail_roi=c['detail_roi'], roi_status='INITIAL_SUGGESTION_REQUIRES_MAIN_SOURCE_ALPHA_REVIEW',
        credit='Hollywood Camera Work / practice footage / results permitted', sourcepage=SOURCE_PAGE, source_page=SOURCE_PAGE,
        ground_truth_available=False, accuracy_metrics=None, input_files=input_files,
        original_source_dir=c['source'], original_movie=c['movie'],
        original_stored_size=c['stored_size'], original_pixel_aspect_ratio=c['par'],
        original_source_fps=c['source_fps'], original_frames=c['native_frames'],
        original_movie_tags={key: stream.get(key) for key in tag_fields},
        missing_original_movie_tags=[key for key in tag_fields if not stream.get(key)],
        prepared_pixel_aspect_ratio='1:1', full_prior_movie_decode_proof=identity(proof_path),
        proof_kind='LEGACY_PRIOR_MOVIE_REUSE_SEPARATE_FROM_NATIVE_V1',
        temporal_mapping='original_index=floor(prepared_index*original_fps/24); source and prediction use identical original indices; no frame interpolation.',
        original_duration_seconds=str(Fraction(c['native_frames'],c['source_fps'])),
        prepared_duration_seconds=str(Fraction(c['frames'],24)),
        future_reel_mapping=f'prepared_index=floor(reel_frame*24/30)%{c["frames"]}; original_index=floor(prepared_index*{c["source_fps"]}/24)',
        color_convention='Preserve original PNG RGB code values and legacy FFmpeg-default decoded cutout display. Interpret those RGB values as sRGB for linear-light PAR correction; this is a display convention derived from Frame Dir Linear=False and Cutout Linear=False, not measured source primaries/transfer.',
        source_png_selected_metadata=c['source_png_selected_metadata'],
        source_metadata_caveat='PNG ancillary metadata is retained in the input snapshot; model image reader used cv2 RGB code values without ICC/gAMA conversion. In particular smoke has gAMA=1.0 but old model/review treated its code values with the sRGB display convention. This reuse preserves that convention rather than silently reinterpreting the old result.',
        resampling='Horizontal PAR correction only; source linear-light Lanczos4. Cutout float32 sRGB EOTF -> premultiply linearRGB by linearalpha -> shared Lanczos4 resize -> clip coverage and premultiplied gamut -> unpremultiply -> sRGB OETF -> RGB8/alpha8. RGB zeroed where quantizedalpha=0. No straight-RGBA interpolation.',
        precision_notes=proof['precision'], frame_mapping=frame_mapping, selected_review=review,
        cache_files_publication='LOCAL_ONLY: do not publish source_reuse or standalone original source assets; main publishes edited demonstration under original terms.',
        elapsed_seconds=round(time.perf_counter()-started,3))
    case_receipt = WORK / f'legacy_{c["id"]}_input.json'
    write_new_json(case_receipt, result)
    log('CASE_COMPLETE', c['id'], 'cacheframes', c['frames'], 'seconds', result['elapsed_seconds'])
    return result


def prepare(snapshot_path, receipt_path):
    frozen = read_json(snapshot_path)
    for c in frozen['cases']:
        if (LAB/'results'/c['id']).exists():
            raise FileExistsError(f'Preserve existing cache; case directory already exists: {c["id"]}')
    if Path(receipt_path).exists():
        raise FileExistsError(receipt_path)
    log('VERIFY_ALL_FROZEN_INPUT_SHA_START')
    before = verify_frozen(frozen)
    control = resampling_control()
    by_path = {row['path']:row for row in frozen['files']}
    results = []
    for c in frozen['cases']:
        results.append(prepare_case(c, by_path))
    log('VERIFY_ALL_FROZEN_INPUT_SHA_END')
    after = verify_frozen(frozen)
    receipt = dict(schema_version=1, status='SUCCEEDED', format='LEGACY_REUSE_INPUT_REFERENCE',
        created_utc=datetime.now(timezone.utc).isoformat(), root=str(ROOT), lab=str(LAB),
        no_new_inference=True, no_download=True, original_inputs_modified=False,
        no_ground_truth=True, no_accuracy_claim=True, frozen_inputs=identity(snapshot_path),
        preparer=identity(__file__), input_sha_verification_before=before,
        input_sha_verification_after=after, resampling_control=control,
        runtime=dict(python=sys.version, numpy=np.__version__, cv2=cv2.__version__, pillow=pillow_version,
            platform=platform.platform(), ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]),
        original_media_proof='Each case binds its own complete prior-ProRes decode ledger and packet clock. No v1 renderer proof is fabricated or reused for these five cases.',
        writer_evidence=dict(video_io=by_path['work/CorridorKey2.0/corridorkey/video_io.py'],
            runtime=by_path['work/CorridorKey2.0/corridorkey/runtime.py'],
            observed='ThreadedVideoWriter accepts bgra64le and encodes prores_ks profile4 yuva444p10le with709 color tags, no explicit conversion matrix filter. Runtime cutout separates RGB and alpha without premultiplication. Settings Cutout Linear=False and Frame Dir Linear=False. Legacy reviews use ffmpeg output pix_fmt rgba without matrix overrides.',
            caveat='Current upstream code and historical settings are bound as local evidence, not a cryptographic historical-code snapshot. Actual MOV headers and default-decode controls are the direct media evidence.'),
        cache_contract='Display-correct square-pixel RGB8 source and straight sRGB-convention RGBA8 prediction, linear alpha8. Explicit sRGB ancillary chunk on new caches declares their working display convention, not newly measured original footage colorimetry.',
        total_prepared_frames=sum(c['frames'] for c in results), cases=results)
    write_new_json(receipt_path, receipt)
    log('LEGACY_PREPARATION_SUCCEEDED', rel(receipt_path), 'cases', len(results), 'frames', receipt['total_prepared_frames'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--freeze-only', action='store_true')
    p.add_argument('--frozen-inputs', type=Path, default=WORK/'legacy_frozen_inputs.json')
    p.add_argument('--receipt', type=Path, default=WORK/'legacy_input_receipt.json')
    args = p.parse_args()
    if args.freeze_only:
        freeze_inputs(args.frozen_inputs.resolve())
    else:
        prepare(args.frozen_inputs.resolve(), args.receipt.resolve())


if __name__ == '__main__':
    main()
