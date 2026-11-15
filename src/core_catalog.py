"""Official Android core artifacts; downloads are not installation evidence."""
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile

import requests

import app_paths
import content_scan as scan
from safe_io import atomic_write_bytes, atomic_write_json

BASE = 'https://buildbot.libretro.com/nightly/android/latest/'
ABIS = {'arm64-v8a': (2, 183), 'armeabi-v7a': (1, 40), 'x86': (1, 3), 'x86_64': (2, 62)}


def validate(core, abi):
    if not isinstance(core, str) or not isinstance(abi, str) or core not in scan.CORE_NAMES or abi not in ABIS:
        raise ValueError('请选择受支持的核心及 RetroArch 应用架构')


def official_get(url):
    response = requests.get(url, timeout=(10, 90), stream=True)
    try:
        response.raise_for_status()
        if not response.url.startswith(url.rsplit('/', 1)[0] + '/'):
            raise ValueError('官方下载发生了非预期跳转')
        chunks, length = [], 0
        for chunk in response.iter_content(1024 * 1024):
            length += len(chunk)
            if length > 512 * 1024 * 1024:
                raise ValueError('官方核心文件超过 512 MB 限制')
            chunks.append(chunk)
        return b''.join(chunks)
    finally:
        response.close()


def info(core):
    if core not in scan.CORE_NAMES:
        raise ValueError('不支持的核心')
    url = 'https://raw.githubusercontent.com/libretro/libretro-core-info/master/' + core + '_libretro.info'
    raw = official_get(url)
    text = raw.decode('utf-8-sig')
    found = re.search(r'^supported_extensions\s*=\s*"([^"\n]*)"', text, re.M)
    if not found:
        raise ValueError('官方核心 info 缺少支持格式')
    return {'source': url, 'extensions': found[1].split('|')}


def download(core, abi):
    validate(core, abi)
    filename = core + '_libretro_android.so'
    url = BASE + abi + '/' + filename + '.zip'
    archive = official_get(url)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = [entry for entry in zipped.infolist() if Path(entry.filename).name == filename]
        if len(entries) != 1 or entries[0].file_size > 512 * 1024 * 1024:
            raise ValueError('官方压缩包的核心文件无效')
        binary = zipped.read(entries[0])
    elf_class, machine = ABIS[abi]
    if (len(binary) < 20 or binary[:4] != b'\x7fELF' or binary[4] != elf_class
            or binary[5] != 1 or struct.unpack_from('<H', binary, 18)[0] != machine):
        raise ValueError('核心 ELF 架构与所选 RetroArch 应用不匹配')
    info_url = 'https://raw.githubusercontent.com/libretro/libretro-core-info/master/' + core + '_libretro.info'
    info = official_get(info_url)
    text = info.decode('utf-8-sig')
    extensions = re.search(r'^supported_extensions\s*=\s*"([^"\n]*)"', text, re.M)
    if not extensions:
        raise ValueError('官方核心 info 缺少支持格式')
    root = app_paths.cache_dir() / 'official-cores' / abi / core
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(root / filename, binary)
    atomic_write_bytes(root / (core + '_libretro.info'), info)
    result = {'core_id': core, 'abi': abi, 'filename': filename, 'source': url,
              'info_source': info_url, 'sha256': hashlib.sha256(binary).hexdigest(),
              'extensions': extensions[1].replace('|', ' '), 'status': 'downloaded',
              'message': '已从官方来源下载并检查架构，尚未安装到 RetroArch'}
    atomic_write_json(root / 'manifest.json', result)
    return result


def transfer(core, abi, device_root):
    validate(core, abi)
    import mtp_runtime as mtp
    if not mtp.is_mtp(device_root):
        raise ValueError('请选择已连接的文件传输掌机')
    root = app_paths.cache_dir() / 'official-cores' / abi / core
    manifest = json.loads((root / 'manifest.json').read_text())
    binary = (root / manifest['filename']).read_bytes()
    if hashlib.sha256(binary).hexdigest() != manifest['sha256']:
        raise ValueError('缓存核心已变化，请重新下载')
    serial, storage, _ = mtp.parse(device_root)
    directory = mtp.uri(serial, storage, 'Download/PLCN-cores')
    target = mtp.join(directory, manifest['filename'])
    mtp.write(target, binary, mtp.digest(mtp.read(target)))
    info_name = core + '_libretro.info'
    info_target = mtp.join(directory, info_name)
    mtp.write(info_target, (root / info_name).read_bytes(), mtp.digest(mtp.read(info_target)))
    return {'status': 'transferred', 'target': target, 'directory': 'Download/PLCN-cores',
            'message': '已传到掌机，待安装。请在 RetroArch → 加载核心 → 安装或恢复核心中选择 Download/PLCN-cores/' + manifest['filename']
                       + '；随后在在线更新器中更新核心信息文件。'}
