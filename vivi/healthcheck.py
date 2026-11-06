"""Container health: no Discord API calls, keys, or message sends."""
import json
from pathlib import Path
import time

def healthy(path,now=None):
    try:
        data=json.loads(Path(path).read_text());age=(now if now is not None else time.time())-float(data['at'])
        return data.get('ready') is True and 0<=age<120
    except (OSError,ValueError,KeyError,TypeError): return False

if __name__=='__main__':
    raise SystemExit(0 if healthy(Path(__file__).resolve().parents[1]/'data'/'heartbeat.json') else 1)
