"""Strict CUE boundary for byte-for-byte 2352-byte sector round-trip validation."""
import hashlib
from pathlib import Path
import re


def fingerprint(path, cancelled=lambda: None, offset=0, length=None):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        stream.seek(offset)
        while length is None or length:
            cancelled()
            chunk=stream.read(1024*1024 if length is None else min(length,1024*1024))
            if not chunk:
                if length: raise ValueError('音轨长度在读取期间变化')
                break
            digest.update(chunk)
            if length is not None: length-=len(chunk)
    return digest.hexdigest()


def layout(cue):
    cue=Path(cue).resolve()
    if cue.stat().st_size>1024*1024: raise ValueError('CUE 超过 1 MiB')
    text=cue.read_text(encoding='utf-8-sig');tracks=[];files=[];current=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.upper().startswith('REM '): continue
        match=re.fullmatch(r'FILE\s+(?:"([^"]+)"|(\S+))\s+BINARY',line,re.I)
        if match:
            name=match[1] or match[2]
            path=(cue.parent/name.replace('\\','/')).resolve()
            if path==cue or not path.is_file() or path.suffix.lower() not in {'.bin','.img','.raw'}:
                raise ValueError('仅支持存在的 BINARY BIN／IMG／RAW 音轨')
            if path in files: raise ValueError('同一 CUE 重复 FILE 声明尚未支持')
            files.append(path);current=None;continue
        match=re.fullmatch(r'TRACK\s+(\d{1,2})\s+(AUDIO|MODE1/2352|MODE2/2352)',line,re.I)
        if match and files:
            current={'number':int(match[1]),'type':match[2].upper(),'file':str(files[-1]),'indices':{},'pregap':0,'postgap':0}
            tracks.append(current);continue
        match=re.fullmatch(r'(INDEX\s+(00|01)|PREGAP|POSTGAP)\s+(\d{2,3}):(\d{2}):(\d{2})',line,re.I)
        if match and current is not None:
            minutes,seconds,frames=map(int,match.group(3,4,5))
            if seconds>=60 or frames>=75: raise ValueError('CUE 时间码无效')
            value=(minutes*60+seconds)*75+frames
            key=match[1].lower()
            if key.startswith('index'):
                index=int(match[2])
                if index in current['indices']: raise ValueError('CUE 重复 INDEX')
                current['indices'][index]=value
            else:
                if current[key]: raise ValueError('CUE 重复间隙声明')
                current[key]=value
            continue
        raise ValueError('尚未支持的 CUE 声明：'+line[:100])
    if not tracks or [track['number'] for track in tracks]!=list(range(1,len(tracks)+1)):
        raise ValueError('CUE 轨号须从 1 连续排列')
    if set(files)!={Path(track['file']) for track in tracks}: raise ValueError('CUE 包含没有 TRACK 的文件')
    for index,track in enumerate(tracks):
        indices=track.pop('indices')
        if 1 not in indices or indices.get(0,indices[1])>indices[1]: raise ValueError('CUE 缺少有效 INDEX 01')
        start=indices.get(0,indices[1]);size=Path(track['file']).stat().st_size
        if size%2352 or size==0: raise ValueError('音轨必须是完整的 2352 字节扇区')
        same=tracks[index+1] if index+1<len(tracks) and tracks[index+1]['file']==track['file'] else None
        end=min(same['indices'].values()) if same else size//2352
        if (index==0 or tracks[index-1]['file']!=track['file']) and start!=0:
            raise ValueError('音轨文件开头有未引用数据，不能证明无损')
        if not start<=indices[1]<end<=size//2352: raise ValueError('CUE 轨道范围无效')
        track.update(offset=start*2352,length=(end-start)*2352,index01=indices[1]-start)
    return tracks


def signature(tracks,cancelled=lambda: None):
    return [{key:track[key] for key in ('number','type','length','index01','pregap','postgap')} |
            {'sha256':fingerprint(track['file'],cancelled,track['offset'],track['length'])} for track in tracks]
