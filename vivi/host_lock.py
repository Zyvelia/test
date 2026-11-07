"""Cross-platform host lock shared by the launcher and updater."""
from contextlib import contextmanager
from pathlib import Path
import os

@contextmanager
def host_lock(root):
    path=Path(root)/'data'/'host.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise RuntimeError('Vivi or another updater is running. Stop Vivi (including tray/startup service), then try again.') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)
