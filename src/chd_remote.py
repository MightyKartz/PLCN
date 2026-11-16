"""Confirmed MTP pull into a persistent computer backup, then the existing converter."""
import json
from pathlib import Path
import re

import app_paths
import chd_cue
import chd_io
import mtp_runtime as mtp
from disc_inspection import Reader, reference_path, parse_references
from safe_io import atomic_write_json
from task_control import TaskCancelled


def convert(plan,selected,cancelled,progress):
    import chd_operations as ops
    rows=[row for row in plan['rows'] if row['id'] in selected]
    if ops.shutil.disk_usage(plan['workspace']).free<ops.RESERVE+6*sum(row['source_bytes'] for row in rows):
        raise ValueError('电脑空间不足，无法保留远程源备份并转换')
    root=Path(plan['workspace'])/('PLCN-SOURCES-'+plan['id']);root.mkdir()
    manifest=app_paths.user_data_dir()/'chd-operations'/plan['id']/'manifest.json';manifest.parent.mkdir(parents=True)
    record={'id':plan['id'],'playlist':plan['playlist'],'system':plan['system'],'created_at':ops.datetime.now(ops.timezone.utc).isoformat(),
            'mode':'from_mtp','status':'pulling','results':[],'error':None,'output_directory':plan['output_directory'],'transfer_sources':[]}
    atomic_write_json(manifest,record)
    try:
        reader=Reader(plan['playlist']);local={}
        inventory={file['path']:file for file in plan['sources']}
        for index,path in enumerate(dict.fromkeys(path for row in rows for path in row['files'])):
            cancelled();progress('拉取电脑源备份：'+path)
            target=root/f'{index:04d}{Path(mtp.parse(path)[2][-1]).suffix}'
            digest=chd_io.copy_to(path,target,cancelled)
            expected=inventory[path]
            if target.stat().st_size!=expected['size'] or expected.get('sha256') and digest!=expected['sha256']:
                raise ValueError('远程源在分析后变化：'+path)
            record['transfer_sources'].append({'path':path,'backup':str(target),'size':target.stat().st_size,'sha256':digest})
            local[path]=target;atomic_write_json(manifest,record)
        mirrors=[]
        for index,row in enumerate(rows):
            source=local[row['files'][0]];lines=[]
            for line in source.read_text(encoding='utf-8-sig').splitlines():
                if re.match(r'^\s*FILE\b',line,re.I):
                    refs,errors=parse_references(line.encode(),'cue')
                    if errors: raise ValueError('CUE FILE 无法解析')
                    location=reader.locate(reference_path(row['path'],refs[0]['value']))
                    if location not in local: raise ValueError('CUE 引用了未确认源文件')
                    line='FILE "'+local[location].name+'" BINARY' if re.search(r'\sBINARY\s*$',line,re.I) else line
                lines.append(line)
            mirror=root/f'disc-{index}.cue';mirror.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            chd_cue.layout(mirror)
            mirrors.append({'path':str(mirror),'core_path':row['core'][0]['path'] if row['core'] else 'DETECT'})
        playlist=root/'sources.lpl';playlist.write_text(json.dumps({'items':mirrors}),encoding='utf-8')
        prepared=ops.analyze({'playlist_path':str(playlist),'system':plan['system'],'workspace':plan['workspace'],'tool':plan['tool']['path']},cancelled,progress)
        by_path={str(Path(mirror['path']).resolve()):row for mirror,row in zip(mirrors,rows)}
        for row in prepared['rows']:
            original=by_path[str(Path(row['path']).resolve())]
            row.update(id=original['id'],origin_path=original['path'],output_name=original['output_name'])
        if (prepared['tool'].get('sha256'),prepared['tool'].get('version'))!=(plan['tool'].get('sha256'),plan['tool'].get('version')):
            raise ValueError('工具在拉取期间变化，请重新分析')
        prepared.update(id=plan['id'],playlist=plan['playlist'],output_directory=plan['output_directory'],transfer_sources=record['transfer_sources'])
        return ops.convert(prepared,[row['id'] for row in rows],cancelled,progress)
    except (OSError,ValueError,RuntimeError,TaskCancelled) as error:
        if manifest.exists(): record=json.loads(manifest.read_text(encoding='utf-8'))
        record.update(status='cancelled' if isinstance(error,TaskCancelled) else 'failed',error=str(error))
        atomic_write_json(manifest,record);raise
