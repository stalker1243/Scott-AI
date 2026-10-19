"""Exercise the installed Qt UI through a private Weston session (no real devices).

Requires Xvfb and Weston. Logs/screenshots contain only the app's synthetic
smoke-test fixtures. The caller can hide the Qt SDK before running this check.
"""
import argparse
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5)


def check(prefix, output, appimage=None):
    prefix=prefix.resolve() if prefix else None
    appimage=appimage.resolve(strict=True) if appimage else None
    if not appimage and (not prefix or not (prefix/'run.sh').is_file() or not (prefix/'launcher/ScottAIQt').is_file()):
        raise ValueError('Expected an installed ScottAI Linux prefix')
    for tool in ('Xvfb','weston'):
        if not shutil.which(tool):
            raise ValueError('Missing test tool: '+tool)
    output.mkdir(parents=True,exist_ok=False)
    runtime=tempfile.TemporaryDirectory(prefix='scott-wayland-session-')
    env={key:value for key,value in os.environ.items() if key not in
         ('QT_QPA_PLATFORM','QT_PLUGIN_PATH','QML2_IMPORT_PATH','QML_IMPORT_PATH','LD_LIBRARY_PATH')
         and not key.upper().endswith(('_API_KEY','_TOKEN'))}
    for variable,directory in [('HOME','home'),('XDG_DATA_HOME','data'),
                               ('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state')]:
        path=output/directory; path.mkdir(mode=0o700); path.chmod(0o700)
        env[variable]=str(path)
    # Unix sockets need a local POSIX filesystem, even when output is a share.
    env['XDG_RUNTIME_DIR']=runtime.name
    env.update(QT_QUICK_BACKEND='software',QSG_RHI_BACKEND='software',WAYLAND_DISPLAY='scott-check',
               WARMUP_MODELS='0',SCOTT_SEMANTIC_MEMORY='0',QT_DEBUG_PLUGINS='1',WAYLAND_DEBUG='client')
    xvfb=weston=None
    results=[]
    try:
        read_fd,write_fd=os.pipe()
        with (output/'xvfb.log').open('w',encoding='utf-8') as log:
            try:
                xvfb=subprocess.Popen(['Xvfb','-displayfd',str(write_fd),'-screen','0','1280x1000x24','-nolisten','tcp'],
                    pass_fds=(write_fd,),stdout=log,stderr=subprocess.STDOUT,env=env)
            finally:
                os.close(write_fd)
            try:
                if not select.select([read_fd],[],[],10)[0]:
                    raise RuntimeError('Xvfb did not provide a display')
                display=os.read(read_fd,64).decode('ascii').strip()
                if not display.isdecimal(): raise RuntimeError('Invalid Xvfb display')
                env['DISPLAY']=':'+display
            finally:
                os.close(read_fd)
        help_text=subprocess.run(['weston','--help'],capture_output=True,text=True,check=True,timeout=10).stdout
        renderer='--renderer=pixman' if '--renderer=' in help_text else '--use-pixman'
        with (output/'weston.log').open('w',encoding='utf-8') as log:
            weston=subprocess.Popen(['weston','--backend=x11-backend.so',renderer,'--width=1280','--height=900',
                '--socket=scott-check','--idle-time=0','--no-config'],env=env,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+10
        socket=Path(env['XDG_RUNTIME_DIR'])/'scott-check'
        while not socket.is_socket() and weston.poll() is None and time.monotonic()<deadline:
            time.sleep(.05)
        if not socket.is_socket(): raise RuntimeError('Weston did not create its Wayland socket')
        for name in ('chat','voice','setup','profile','logs',*('chat-layout-'+str(index) for index in range(1,11))):
            log_path=output/(name+'.log')
            flag='--smoke-chat-layout' if name.startswith('chat-layout-') else '--smoke-'+name
            command=[str(appimage),'--appimage-extract-and-run',flag] if appimage else ['/bin/bash',str(prefix/'run.sh'),flag]
            with log_path.open('w',encoding='utf-8') as log:
                result=subprocess.run(command,cwd=output,env=env,
                    stdout=log,stderr=subprocess.STDOUT,timeout=45)
            log=log_path.read_text(encoding='utf-8',errors='replace')
            # Prove the wrapper selected the bundled native plugin; merely
            # listing an available plugin in Qt diagnostics is insufficient.
            loaded=any('libqwayland' in line and 'loaded library' in line and 'unloaded library' not in line
                       for line in log.splitlines())
            app_id='set_app_id("com.scottai.launcher")' in log
            results.append({'name':name,'exit_code':result.returncode,'native_wayland_plugin_loaded':loaded,
                            'desktop_app_id_matches':app_id})
            print(json.dumps(results[-1]),flush=True)
        summary={'checks':results,'software_rendering':True,'physical_input':False,
                 'appimage_extract_and_run':bool(appimage),
                 'sdk_path_visible':bool(os.getenv('QT_ROOT_DIR') and Path(os.environ['QT_ROOT_DIR']).exists())}
        (output/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        return 0 if all(row['exit_code']==0 and row['native_wayland_plugin_loaded'] and row['desktop_app_id_matches'] for row in results) else 1
    finally:
        stop(weston); stop(xvfb); runtime.cleanup()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--prefix',type=Path)
    source.add_argument('--appimage',type=Path,help='Run an actual image using extract-and-run (without FUSE)')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    output=args.output or Path(tempfile.gettempdir())/('scott-wayland-check-'+str(os.getpid()))
    return check(args.prefix,output.resolve(),args.appimage)


if __name__=='__main__':
    raise SystemExit(main())
