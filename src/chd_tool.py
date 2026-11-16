"""Invoke an explicitly selected local MAME chdman without a shell."""
from pathlib import Path
import re
import shutil
import subprocess

from chd_cue import fingerprint

SOURCE='https://www.mamedev.org/release.html'


def capability(value=''):
    if not isinstance(value,str): raise ValueError('chdman 路径无效')
    executable=str(Path(value).expanduser().resolve()) if value else shutil.which('chdman')
    if not executable or not Path(executable).is_file():
        return {'available':False,'path':value,'source':SOURCE,'message':'未找到 chdman，请从官方 MAME 工具获取，或指定本机程序'}
    try:
        result=subprocess.run([executable],capture_output=True,text=True,errors='replace',timeout=10)
        banner=result.stdout+result.stderr
        version=re.search(r'CHD\) manager ([0-9]+\.[0-9]+)',banner)
        if not version: raise ValueError('所选程序不是可识别的 MAME chdman')
        for command in ('createcd','verify','extractcd'):
            if command not in banner: raise ValueError('chdman 缺少所需命令：'+command)
        return {'available':True,'path':executable,'version':version[1],'sha256':fingerprint(executable),
                'source':SOURCE,'provenance':'user_supplied_unverified','message':'本机工具已识别；来源由用户核对，未随应用分发或下载'}
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:
        return {'available':False,'path':executable,'source':SOURCE,'message':str(error)}


def run(tool,args,directory,cancelled,log):
    log=Path(log)
    with log.open('ab') as output:
        output.write(('\n'+repr([tool,*args])+'\n').encode());output.flush()
        process=subprocess.Popen([tool,*args],stdout=output,stderr=subprocess.STDOUT,cwd=directory)
        try:
            while True:
                cancelled()
                try:
                    code=process.wait(timeout=.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
        if code:
            with log.open('rb') as stream:
                stream.seek(max(0,log.stat().st_size-3000))
                detail=stream.read().decode('utf-8',errors='replace')
            raise RuntimeError('chdman 执行失败：'+detail)
