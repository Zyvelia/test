"""Restart transient bot crashes; stop on clean exits or configuration errors."""
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    folder=ROOT/'data'/'logs'; folder.mkdir(parents=True,exist_ok=True)
    delay=5
    try:
        while True:
            path=folder/'bot.log'
            if path.exists() and path.stat().st_size>2_000_000:
                old=folder/'bot.previous.log'
                old.unlink(missing_ok=True); path.replace(old)
            started=time.monotonic()
            with path.open('a',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,'-u','-m','aurora.bot'],cwd=ROOT,
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
                try:
                    for line in process.stdout:
                        print(line,end='',flush=True); log.write(line); log.flush()
                        if path.stat().st_size>2_000_000:
                            log.seek(0); log.truncate(); log.write('[Log truncated at 2 MB; newest output follows.]\n')
                    code=process.wait()
                except KeyboardInterrupt:
                    if process.poll() is None: process.terminate()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
                    return
            if code in (0,2):
                print('Stopped. Fix any configuration error above, then restart.' if code==2 else 'Bot shut down normally.')
                return
            if time.monotonic()-started>300: delay=5
            print(f'Bot crashed (exit {code}). Restarting in {delay}s. See data/logs/bot.log. Ctrl+C stops restarts.',flush=True)
            time.sleep(delay); delay=min(delay*2,120)
    except KeyboardInterrupt:
        return

if __name__=='__main__': main()
