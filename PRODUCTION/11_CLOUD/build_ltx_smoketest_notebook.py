#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the isolated post-keyframe Colab notebook for Plyazh."""

import hashlib
import json
import os
from pathlib import Path


HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "PLYAZH_LTX_SMOKETEST_COLAB.ipynb")
MANIFEST_OUT = os.path.join(HERE, "keyframes_v2_manifest.json")
LOCAL_KEYFRAMES = os.path.abspath(os.path.join(HERE, "..", "12_CHATGPT", "keyframes_v2"))


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


cells = []

cells.append(md("""# «Пляж» — 4x-UltraSharp + LTX smoke-test

Изолированный посткадровый контур для принятого комплекта `keyframes_v2`.

- проверяет 59 PNG против `shots_arcane.json`;
- увеличивает все кадры моделью **4x-UltraSharp**, затем уменьшает модельный 4x-результат до 1920×1080 методом bicubic — **LANCZOS не используется**;
- применяет линейную экспокоррекцию **+1/3 EV только к SH022 и SH024**;
- перезапускает ComfyUI, полностью освобождая апскейлер;
- генерирует LTX-Video 0.9.5 только для **SH003 и SH001**, 73 кадра / 24 fps (~3.04 с);
- пишет wall time, peak VRAM, QC движения/чёрных кадров и сохраняет контрольные полосы.

SDXL, Arcane-LoRA и InstantID здесь не устанавливаются и не загружаются. Полного video batch в ноутбуке нет.

> Runtime → Change runtime type → GPU → T4
"""))

cells.append(md("## 1. Проверка T4 и режима точности"))
cells.append(code("""!nvidia-smi
import hashlib, json, os, re, shutil, subprocess, sys, threading, time, urllib.request, uuid
from pathlib import Path

import torch

if not torch.cuda.is_available():
    raise RuntimeError('GPU не выдан: Runtime → Change runtime type → GPU')
gpu = torch.cuda.get_device_properties(0)
gpu_name = gpu.name
gpu_total_gb = gpu.total_memory / 1024**3
print(f'GPU: {gpu_name} | VRAM: {gpu_total_gb:.2f} GiB')
print('bf16 supported:', torch.cuda.is_bf16_supported())
print('Режим проекта: fp16; flash-attention не устанавливается и не используется')
if 'T4' in gpu_name.upper() and torch.cuda.is_bf16_supported():
    print('ВНИМАНИЕ: runtime сообщает bf16, но проект всё равно принудительно использует fp16')
if gpu_total_gb < 14.0:
    raise RuntimeError(f'Недостаточно VRAM для утверждённого T4 smoke-test: {gpu_total_gb:.1f} GiB')
"""))

cells.append(md("""## 2. Google Drive и принятые исходники

Положите локальную папку в один из двух приватных путей Drive:

- `MyDrive/PLYAZH_ARCANE/PRODUCTION/12_CHATGPT/keyframes_v2/`, или
- `MyDrive/PLYAZH_ARCANE/keyframes_v2/` — простой вариант для drag-and-drop.

Ноутбук не принимает старые `01_keyframes` и не подменяет недостающие файлы.
"""))
cells.append(code("""from google.colab import drive
drive.mount('/content/drive')

PROJ = Path('/content/drive/MyDrive/PLYAZH_ARCANE')
SOURCE_CANDIDATES = [
    PROJ / 'PRODUCTION/12_CHATGPT/keyframes_v2',
    PROJ / 'keyframes_v2',
]
found_sources = [path for path in SOURCE_CANDIDATES if path.is_dir()]
if len(found_sources) != 1:
    raise RuntimeError(f'Нужен ровно один каталог keyframes_v2; найдено: {found_sources}')
SRC = found_sources[0]
UPSCALED = PROJ / 'PRODUCTION/12_CHATGPT/upscaled_v2'
PRE_CC = UPSCALED / '_pre_cc'
CLIPS = PROJ / 'PRODUCTION/12_CHATGPT/ltx_smoketest_v2'
QC_DIR = CLIPS / '_qc'
TELEMETRY_PATH = CLIPS / 'telemetry.json'
for path in (UPSCALED, PRE_CC, CLIPS, QC_DIR):
    path.mkdir(parents=True, exist_ok=True)

ASSET_BASE_URL = 'https://raw.githubusercontent.com/Ejonnyss/film/main/PRODUCTION/11_CLOUD'
PACK = PROJ / 'shots_arcane.json'
urllib.request.urlretrieve(f'{ASSET_BASE_URL}/shots_arcane.json', PACK)
pack = json.loads(PACK.read_text(encoding='utf-8'))
SHOTS = pack['shots']
expected = [s['shot_id'] + '.png' for s in SHOTS]
MANIFEST_PATH = Path('/content/keyframes_v2_manifest.json')
urllib.request.urlretrieve(f'{ASSET_BASE_URL}/keyframes_v2_manifest.json', MANIFEST_PATH)
manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
if sorted(manifest['files']) != sorted(expected):
    raise RuntimeError('SHA manifest не совпадает со списком shot_id')

actual = sorted(p.name for p in SRC.glob('*.png'))
missing = sorted(set(expected) - set(actual))
extra = sorted(set(actual) - set(expected))
if len(actual) != 59 or missing or extra:
    raise RuntimeError(f'Комплект не принят: count={len(actual)}/59 missing={missing} extra={extra}')

from PIL import Image
bad = []
def file_sha256(path, block=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block), b''):
            h.update(chunk)
    return h.hexdigest()

for name in expected:
    try:
        with Image.open(SRC / name) as im:
            im.load()
            if im.size != (1672, 941):
                bad.append((name, im.size))
        spec = manifest['files'][name]
        if (SRC / name).stat().st_size != spec['size'] or file_sha256(SRC / name) != spec['sha256']:
            bad.append((name, 'SHA/size mismatch with accepted local frame'))
    except Exception as exc:
        bad.append((name, repr(exc)))
if bad:
    raise RuntimeError(f'Повреждены/неверного размера: {bad}')
print('Комплект подтверждён: 59/59 PNG, 1672x941, SHA-256 match, missing=[], extra=[]')
"""))

cells.append(md("""## 3. Минимальная установка ComfyUI

Устанавливаются только core ComfyUI и VideoHelperSuite. Ноды/модели SDXL и InstantID отсутствуют.
"""))
cells.append(code("""import pathlib

COMFY_COMMIT = '83082a51c420a364b15ea5f40d61da74e35b2da5'
VHS_COMMIT = '4ee72c065db22c9d96c2427954dc69e7b908444b'

def run(cmd, cwd=None):
    print('+', ' '.join(map(str, cmd)))
    subprocess.run(list(map(str, cmd)), cwd=cwd, check=True)

def ensure_repo(url, path, commit):
    path = Path(path)
    if not (path / '.git').exists():
        run(['git', 'clone', '--filter=blob:none', '--no-checkout', url, path])
    run(['git', 'fetch', '--depth', '1', 'origin', commit], cwd=path)
    run(['git', 'checkout', '--detach', commit], cwd=path)
    got = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()
    if got != commit:
        raise RuntimeError((path, got, commit))

ensure_repo('https://github.com/Comfy-Org/ComfyUI.git', '/content/ComfyUI', COMFY_COMMIT)
run([sys.executable, '-m', 'pip', 'install', '-q', '-r', '/content/ComfyUI/requirements.txt'])
node_root = Path('/content/ComfyUI/custom_nodes')
node_root.mkdir(parents=True, exist_ok=True)
vhs = node_root / 'ComfyUI-VideoHelperSuite'
ensure_repo('https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git', vhs, VHS_COMMIT)
if (vhs / 'requirements.txt').exists():
    run([sys.executable, '-m', 'pip', 'install', '-q', '-r', vhs / 'requirements.txt'])
run([sys.executable, '-m', 'pip', 'install', '-q', 'opencv-python-headless', 'imageio-ffmpeg'])

for forbidden in ('ComfyUI_InstantID', 'ComfyUI-ReActor', 'ComfyUI-PuLID'):
    path = node_root / forbidden
    if path.exists():
        raise RuntimeError(f'Удалите запрещённую для этого этапа ноду: {path}')
print('Минимальная установка готова; SDXL/InstantID не устанавливались')
"""))

cells.append(md("## 4. Только три требуемые модели"))
cells.append(code("""import hashlib

M = Path('/content/ComfyUI/models')
for sub in ('upscale_models', 'checkpoints', 'text_encoders'):
    (M / sub).mkdir(parents=True, exist_ok=True)

def sha256(path, block=16 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(block), b''):
            h.update(chunk)
    return h.hexdigest()

def fetch(spec):
    path = Path(spec['path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    def valid():
        return path.exists() and path.stat().st_size == spec['size'] and sha256(path) == spec['sha256']
    if valid():
        print('OK cache:', path.name)
        return
    if path.exists():
        path.unlink()
    run(['wget', '-c', '--tries=5', '--timeout=30', '--show-progress', '-O', path, spec['url']])
    if not valid():
        raise RuntimeError(f'checksum/size mismatch: {path}')
    print('verified:', path.name)

MODEL_SPECS = [
    {'path': M/'upscale_models/4x-UltraSharp.pth', 'size': 66961958,
     'sha256': 'a5812231fc936b42af08a5edba784195495d303d5b3248c24489ef0c4021fe01',
     'url': 'https://huggingface.co/uwg/upscaler/resolve/main/ESRGAN/4x-UltraSharp.pth'},
    {'path': M/'checkpoints/ltx-video-2b-v0.9.5.safetensors', 'size': 6340729500,
     'sha256': '720d15c9f19f7d0f6b2a92bbbc34410e2cfb2f6856a100b38f734fbf973d4adf',
     'url': 'https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors'},
    {'path': M/'text_encoders/t5xxl_fp16.safetensors', 'size': 9787841024,
     'sha256': '6e480b09fae049a72d2a8c5fbccb8d3e92febeb233bbe9dfe7256958a9167635',
     'url': 'https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors'},
]
for spec in MODEL_SPECS:
    fetch(spec)

for forbidden in (
    M/'checkpoints/sd_xl_base_1.0.safetensors',
    M/'instantid/ip-adapter.bin',
    M/'controlnet/instantid_controlnet.safetensors',
):
    if forbidden.exists():
        raise RuntimeError(f'В чистом runtime не должен присутствовать запрещённый файл: {forbidden}')
print('Проверены только 4x-UltraSharp + LTX 0.9.5 + T5XXL fp16')
"""))

cells.append(md("## 5. Запуск ComfyUI в безопасном fp16/low-VRAM режиме"))
cells.append(code("""LOG_PATH = Path('/content/comfy_ltx_smoke.log')
proc = None
log_handle = None

def stop_comfy():
    global proc, log_handle
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=10)
    if log_handle is not None and not log_handle.closed:
        log_handle.close()
    proc = None
    torch.cuda.empty_cache()

def start_comfy():
    global proc, log_handle
    stop_comfy()
    log_handle = open(LOG_PATH, 'w')
    cmd = [
        'python', 'main.py', '--listen', '127.0.0.1', '--port', '8188',
        '--lowvram', '--force-fp16', '--fp32-vae', '--preview-method', 'none',
    ]
    proc = subprocess.Popen(cmd, cwd='/content/ComfyUI', stdout=log_handle, stderr=subprocess.STDOUT)
    for second in range(240):
        try:
            urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=2)
            print('ComfyUI готов за', second, 'с | args:', ' '.join(cmd[2:]))
            return
        except Exception:
            if proc.poll() is not None:
                break
            time.sleep(1)
    tail = LOG_PATH.read_text(errors='replace')[-8000:] if LOG_PATH.exists() else ''
    raise RuntimeError('ComfyUI не стартовал:\\n' + tail)

start_comfy()
objects = json.loads(urllib.request.urlopen('http://127.0.0.1:8188/object_info').read())
required = {
    'LoadImage', 'UpscaleModelLoader', 'ImageUpscaleWithModel', 'ImageScale', 'SaveImage',
    'CheckpointLoaderSimple', 'CLIPLoader', 'CLIPTextEncode', 'LTXVPreprocess',
    'LTXVImgToVideo', 'LTXVConditioning', 'LTXVScheduler', 'KSamplerSelect',
    'SamplerCustom', 'VAEDecode', 'VHS_VideoCombine',
}
missing_nodes = sorted(required - set(objects))
if missing_nodes:
    raise RuntimeError(f'Отсутствуют ноды: {missing_nodes}\\n' + LOG_PATH.read_text(errors='replace')[-8000:])
print('Официальная LTX 0.9.5 цепочка найдена:', sorted(required))
"""))

cells.append(md("## 6. API-клиент с wall time и peak VRAM"))
cells.append(code("""SRV = 'http://127.0.0.1:8188'
CID = str(uuid.uuid4())

def gpu_memory_mb():
    out = subprocess.check_output([
        'nvidia-smi', '--query-gpu=memory.used,memory.total',
        '--format=csv,noheader,nounits'], text=True).strip().splitlines()[0]
    used, total = [float(x.strip()) for x in out.split(',')]
    return used, total

def queue(workflow, label, timeout=3600):
    samples = []
    stop_event = threading.Event()
    def poll():
        while not stop_event.is_set():
            try:
                samples.append((time.monotonic(),) + gpu_memory_mb())
            except Exception:
                pass
            stop_event.wait(0.25)
    watcher = threading.Thread(target=poll, daemon=True)
    watcher.start()
    started = time.monotonic()
    try:
        data = json.dumps({'prompt': workflow, 'client_id': CID}).encode()
        req = urllib.request.Request(f'{SRV}/prompt', data=data, headers={'Content-Type': 'application/json'})
        try:
            response = json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(exc.read().decode('utf-8', 'replace')) from exc
        if response.get('node_errors'):
            raise RuntimeError(json.dumps(response['node_errors'], ensure_ascii=False, indent=2))
        pid = response['prompt_id']
        while time.monotonic() - started < timeout:
            history = json.loads(urllib.request.urlopen(f'{SRV}/history/{pid}').read())
            if pid in history:
                status = history[pid].get('status', {})
                if status.get('status_str') == 'error':
                    raise RuntimeError(json.dumps(status, ensure_ascii=False, indent=2))
                outputs = []
                for node in history[pid].get('outputs', {}).values():
                    for key in ('images', 'gifs', 'videos'):
                        for item in node.get(key, []):
                            outputs.append('/content/ComfyUI/output/' + os.path.join(item.get('subfolder', ''), item['filename']))
                if not outputs:
                    raise RuntimeError(f'{label}: workflow завершился без файла')
                elapsed = time.monotonic() - started
                used_values = [x[1] for x in samples]
                total_values = [x[2] for x in samples]
                return outputs, {
                    'label': label,
                    'wall_seconds': round(elapsed, 2),
                    'peak_vram_mb': round(max(used_values), 1) if used_values else None,
                    'total_vram_mb': round(max(total_values), 1) if total_values else None,
                }
            time.sleep(2)
        raise TimeoutError(f'{label}: timeout {timeout}s')
    except Exception as exc:
        tail = LOG_PATH.read_text(errors='replace')[-12000:] if LOG_PATH.exists() else ''
        low = tail.lower()
        hint = ''
        if 'nan' in low or 'out of memory' in low or 'cuda error' in low:
            hint = '\\nT4 fp16/VRAM failure detected; stop, do not retry blindly.'
        raise RuntimeError(f'{label}: {exc}{hint}\\n--- comfy tail ---\\n{tail}') from exc
    finally:
        stop_event.set(); watcher.join(timeout=2)

print('API-клиент и VRAM watcher готовы')
"""))

cells.append(md("""## 7. Модельный апскейл всех 59 кадров

Цепочка: `4x-UltraSharp → bicubic downsample/crop → 1920×1080`.
Метод LANCZOS отсутствует. Исходники `keyframes_v2` не изменяются.
"""))
cells.append(code("""COMFY_INPUT = Path('/content/ComfyUI/input')
COMFY_INPUT.mkdir(parents=True, exist_ok=True)

def wf_upscale(image_name):
    workflow = {
        '1': {'class_type': 'LoadImage', 'inputs': {'image': image_name}},
        '2': {'class_type': 'UpscaleModelLoader', 'inputs': {'model_name': '4x-UltraSharp.pth'}},
        '3': {'class_type': 'ImageUpscaleWithModel', 'inputs': {'upscale_model': ['2', 0], 'image': ['1', 0]}},
        '4': {'class_type': 'ImageScale', 'inputs': {
            'image': ['3', 0], 'upscale_method': 'bicubic',
            'width': 1920, 'height': 1080, 'crop': 'center'}},
        '5': {'class_type': 'SaveImage', 'inputs': {'filename_prefix': 'upscaled_v2', 'images': ['4', 0]}},
    }
    if 'lanczos' in json.dumps(workflow).lower():
        raise RuntimeError('LANCZOS запрещён')
    return workflow

upscale_metrics = []
for index, shot in enumerate(SHOTS, 1):
    sid = shot['shot_id']
    src = SRC / f'{sid}.png'
    dst = UPSCALED / f'{sid}.png'
    valid_cache = False
    if dst.exists():
        try:
            with Image.open(dst) as im:
                valid_cache = im.size == (1920, 1080)
        except Exception:
            valid_cache = False
    if valid_cache:
        print(f'[{index:02d}/59] {sid} cache')
        continue
    input_name = f'accepted_{sid}.png'
    shutil.copy2(src, COMFY_INPUT / input_name)
    outputs, metric = queue(wf_upscale(input_name), f'upscale_{sid}', timeout=1200)
    image_outputs = [Path(p) for p in outputs if Path(p).suffix.lower() in {'.png', '.jpg', '.webp'}]
    if not image_outputs:
        raise RuntimeError(f'{sid}: апскейлер не вернул изображение')
    shutil.copy2(image_outputs[0], dst)
    with Image.open(dst) as im:
        if im.size != (1920, 1080):
            raise RuntimeError(f'{sid}: output size {im.size}')
    upscale_metrics.append(metric)
    print(f"[{index:02d}/59] {sid} OK | {metric['wall_seconds']}s | peak {metric['peak_vram_mb']} MiB")

missing_upscaled = []
for shot in SHOTS:
    path = UPSCALED / f"{shot['shot_id']}.png"
    try:
        with Image.open(path) as im:
            if im.size != (1920, 1080): missing_upscaled.append((path.name, im.size))
    except Exception as exc:
        missing_upscaled.append((path.name, repr(exc)))
if missing_upscaled:
    raise RuntimeError(f'Апскейл неполон: {missing_upscaled}')
print('Апскейл подтверждён физически: 59/59 PNG 1920x1080; LANCZOS не использован')
"""))

cells.append(md("""## 8. Только SH022/SH024: +1/3 EV в линейном свете

Одинаковый множитель применяется ко всем RGB-каналам. Палитра и остальные 57 кадров не меняются.
До коррекции сохраняются копии в `_pre_cc/`.
"""))
cells.append(code("""import numpy as np

CC_IDS = ('S01_SH022', 'S01_SH024')
EV = 1.0 / 3.0
GAIN = 2.0 ** EV

def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

def linear_to_srgb(x):
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1/2.4) - 0.055)

for sid in CC_IDS:
    dst = UPSCALED / f'{sid}.png'
    base = PRE_CC / f'{sid}.png'
    if not base.exists():
        shutil.copy2(dst, base)
    with Image.open(base) as im:
        arr = np.asarray(im.convert('RGB'), dtype=np.float32) / 255.0
    corrected = linear_to_srgb(np.clip(srgb_to_linear(arr) * GAIN, 0.0, 1.0))
    out = np.clip(np.rint(corrected * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(out, 'RGB').save(dst, compress_level=4)
    print(sid, f'+{EV:.3f} EV', 'mean before/after', round(float(arr.mean()), 5), round(float(corrected.mean()), 5))

# Контрольная полоса SH021–SH025: верх до коррекции для 022/024, низ после.
ids = [f'S01_SH{i:03d}' for i in range(21, 26)]
thumbs_before = []
thumbs_after = []
for sid in ids:
    before_path = PRE_CC / f'{sid}.png' if sid in CC_IDS else UPSCALED / f'{sid}.png'
    if not before_path.exists(): before_path = UPSCALED / f'{sid}.png'
    thumbs_before.append(Image.open(before_path).convert('RGB').resize((384, 216)))
    thumbs_after.append(Image.open(UPSCALED / f'{sid}.png').convert('RGB').resize((384, 216)))
sheet = Image.new('RGB', (384 * 5, 216 * 2), (8, 12, 18))
for i, im in enumerate(thumbs_before): sheet.paste(im, (i * 384, 0))
for i, im in enumerate(thumbs_after): sheet.paste(im, (i * 384, 216))
cc_sheet = UPSCALED / '_cc_SH021_SH025_before_after.jpg'
sheet.save(cc_sheet, quality=92)
display(sheet.resize((960, 216)))
print('Цветокоррекция завершена только для:', CC_IDS, '| QC:', cc_sheet)
"""))

cells.append(md("""## 9. Освобождение апскейлера перед LTX

ComfyUI полностью перезапускается. Это гарантирует, что 4x-UltraSharp выгружен, а SDXL/InstantID никогда не загружались.
"""))
cells.append(code("""stop_comfy()
subprocess.run(['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader'], check=False)
start_comfy()
print('ComfyUI перезапущен; следующий workflow содержит только LTX/T5')
"""))

cells.append(md("""## 10. LTX 0.9.5 smoke-test: только SH003 и SH001

Базовая проба: **768×448, 73 кадра, 24 fps, 30 steps, fp16**. `img_compression=20` вместо стандартного 35, чтобы меньше разрушать живописную фактуру входа.

Если появятся NaN, CUDA error или чёрные кадры — ячейка останавливается. Повторять полный batch запрещено.
"""))
cells.append(code("""SMOKE_IDS = ('S01_SH003', 'S01_SH001')
LTX_WIDTH = 768
LTX_HEIGHT = 448
LTX_FRAMES = 73
LTX_FPS = 24
LTX_STEPS = 30

def wf_i2v(image_name, prompt, negative, seed):
    return {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'ltx-video-2b-v0.9.5.safetensors'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {
            'clip_name': 't5xxl_fp16.safetensors', 'type': 'ltxv', 'device': 'default'}},
        '3': {'class_type': 'LoadImage', 'inputs': {'image': image_name}},
        '4': {'class_type': 'LTXVPreprocess', 'inputs': {'image': ['3', 0], 'img_compression': 20}},
        '5': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
        '6': {'class_type': 'CLIPTextEncode', 'inputs': {'text': negative, 'clip': ['2', 0]}},
        '7': {'class_type': 'LTXVImgToVideo', 'inputs': {
            'positive': ['5', 0], 'negative': ['6', 0], 'vae': ['1', 2], 'image': ['4', 0],
            'width': LTX_WIDTH, 'height': LTX_HEIGHT, 'length': LTX_FRAMES,
            'batch_size': 1, 'strength': 1.0}},
        '8': {'class_type': 'LTXVConditioning', 'inputs': {
            'positive': ['7', 0], 'negative': ['7', 1], 'frame_rate': float(LTX_FPS)}},
        '9': {'class_type': 'LTXVScheduler', 'inputs': {
            'steps': LTX_STEPS, 'max_shift': 2.05, 'base_shift': 0.95,
            'stretch': True, 'terminal': 0.1, 'latent': ['7', 2]}},
        '10': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
        '11': {'class_type': 'SamplerCustom', 'inputs': {
            'model': ['1', 0], 'add_noise': True, 'noise_seed': seed, 'cfg': 3.0,
            'positive': ['8', 0], 'negative': ['8', 1], 'sampler': ['10', 0],
            'sigmas': ['9', 0], 'latent_image': ['7', 2]}},
        '12': {'class_type': 'VAEDecode', 'inputs': {'samples': ['11', 0], 'vae': ['1', 2]}},
        '13': {'class_type': 'VHS_VideoCombine', 'inputs': {
            'images': ['12', 0], 'frame_rate': LTX_FPS, 'loop_count': 0,
            'filename_prefix': 'ltx_smoke', 'format': 'video/h264-mp4',
            'pix_fmt': 'yuv420p', 'crf': 18, 'save_metadata': True,
            'trim_to_audio': False, 'pingpong': False, 'save_output': True}},
    }

by_id = {s['shot_id']: s for s in SHOTS}
telemetry = {
    'gpu': gpu_name,
    'precision': 'fp16 model/T5, fp32 VAE',
    'bf16_used': False,
    'flash_attention_used': False,
    'ltx': {'version': '0.9.5-2b', 'width': LTX_WIDTH, 'height': LTX_HEIGHT,
            'frames': LTX_FRAMES, 'fps': LTX_FPS, 'steps': LTX_STEPS},
    'clips': [],
}

for sid in SMOKE_IDS:
    shot = by_id[sid]
    src = UPSCALED / f'{sid}.png'
    input_name = f'ltx_{sid}.png'
    shutil.copy2(src, COMFY_INPUT / input_name)
    dst = CLIPS / f'{sid}.mp4'
    outputs, metric = queue(
        wf_i2v(input_name, shot['motion_prompt'], shot['motion_negative'], shot['seed']),
        f'ltx_{sid}', timeout=3600)
    video_outputs = [Path(p) for p in outputs if Path(p).suffix.lower() in {'.mp4', '.webm', '.mov'}]
    if not video_outputs:
        raise RuntimeError(f'{sid}: LTX не вернул видео')
    shutil.copy2(video_outputs[0], dst)
    metric.update({'shot_id': sid, 'path': str(dst)})
    telemetry['clips'].append(metric)
    TELEMETRY_PATH.write_text(json.dumps(telemetry, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"{sid}: wall {metric['wall_seconds']}s | peak {metric['peak_vram_mb']} MiB")
print('LTX smoke render finished; full batch remains disabled')
"""))

cells.append(md("## 11. QC фактуры, движения, чёрных кадров и VRAM-рекомендация"))
cells.append(code("""import cv2
from IPython.display import Video, display

def probe_clip(path, sid):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok: break
        frames.append(frame)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or LTX_FPS)
    cap.release()
    if not frames:
        raise RuntimeError(f'{sid}: клип не декодируется')
    means = [float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean()) for f in frames]
    black_fraction = sum(x < 3.0 for x in means) / len(means)
    diffs = [float(cv2.absdiff(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY),
                               cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)).mean())
             for a, b in zip(frames, frames[1:])]
    motion_score = float(np.mean(diffs)) if diffs else 0.0
    lap = [float(cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
           for f in frames]
    picks = [0, len(frames)//2, len(frames)-1]
    sample_images = [cv2.cvtColor(frames[i], cv2.COLOR_BGR2RGB) for i in picks]
    strip = Image.new('RGB', (LTX_WIDTH * 3, LTX_HEIGHT), (0, 0, 0))
    for i, arr in enumerate(sample_images): strip.paste(Image.fromarray(arr), (i * LTX_WIDTH, 0))
    strip_path = QC_DIR / f'{sid}_start_mid_end.jpg'
    strip.save(strip_path, quality=92)
    result = {
        'decoded_frames': len(frames), 'decoded_fps': round(fps, 3),
        'clip_seconds': round(len(frames) / fps, 3),
        'black_fraction': round(black_fraction, 4),
        'motion_score_mean_absdiff': round(motion_score, 4),
        'texture_laplacian_start_mid_end': [round(lap[i], 2) for i in picks],
        'qc_strip': str(strip_path),
    }
    if black_fraction > 0.02 or max(means) < 8.0:
        raise RuntimeError(f'{sid}: чёрные кадры/FP16 instability: {result}')
    if motion_score < 0.35:
        result['warning'] = 'Движение очень слабое: визуально проверить как почти статичный клип'
    return result, strip

for clip_metric in telemetry['clips']:
    sid = clip_metric['shot_id']
    qc, strip = probe_clip(CLIPS / f'{sid}.mp4', sid)
    clip_metric['qc'] = qc
    display(strip.resize((1152, 224)))
    display(Video(str(CLIPS / f'{sid}.mp4'), embed=True, width=768))
    print(sid, json.dumps({
        'wall_seconds': clip_metric['wall_seconds'],
        'peak_vram_mb': clip_metric['peak_vram_mb'],
        **qc,
    }, ensure_ascii=False, indent=2))

peak = max(x['peak_vram_mb'] for x in telemetry['clips'] if x['peak_vram_mb'] is not None)
total = max(x['total_vram_mb'] for x in telemetry['clips'] if x['total_vram_mb'] is not None)
headroom = total - peak
if headroom >= 4500:
    recommendation = 'Есть запас: следующим отдельным тестом можно пробовать 896x512 ИЛИ 97 кадров, но не оба параметра сразу.'
elif headroom >= 2500:
    recommendation = 'Запас умеренный: разрешение оставить 768x448; допустим отдельный тест 81/97 кадров.'
else:
    recommendation = 'Запаса мало: не повышать ни разрешение, ни кадры на T4.'
telemetry['peak_vram_mb_overall'] = peak
telemetry['vram_headroom_mb'] = round(headroom, 1)
telemetry['capacity_recommendation'] = recommendation
TELEMETRY_PATH.write_text(json.dumps(telemetry, ensure_ascii=False, indent=2), encoding='utf-8')
print('\\nПИК VRAM:', peak, 'MiB | свободно:', round(headroom, 1), 'MiB')
print(recommendation)
print('Телеметрия:', TELEMETRY_PATH)
print('\\nСТОП. Покажите два MP4, две полосы start/mid/end и telemetry.json. Полный batch запрещён до нового ok.')
"""))

cells.append(md("""## 12. Ручной стоп

Ноутбук намеренно заканчивается после двух клипов. Здесь нет цикла по 59 планам и нет статичного fallback.

При слабой фактуре, дрейфе лица, слабом движении, NaN или чёрных кадрах результат нужно признать слабым и не продолжать batch.
"""))


local_source = Path(LOCAL_KEYFRAMES)
if not local_source.is_dir():
    raise FileNotFoundError(local_source)
manifest_files = {}
for path in sorted(local_source.glob("*.png")):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    manifest_files[path.name] = {"size": path.stat().st_size, "sha256": h.hexdigest()}
if len(manifest_files) != 59:
    raise RuntimeError(f"manifest source count {len(manifest_files)}/59")
with open(MANIFEST_OUT, "w", encoding="utf-8") as f:
    json.dump({"shot_count": 59, "width": 1672, "height": 941, "files": manifest_files},
              f, ensure_ascii=False, indent=2)

notebook = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"provenance": [], "gpuType": "T4", "toc_visible": True},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(notebook, f, ensure_ascii=False, indent=1)

print("OK ->", OUT)
print("Manifest ->", MANIFEST_OUT)
print("Ячеек:", len(cells))
