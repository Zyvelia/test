"""Cross-platform process lock; do not remove the lock file while a process owns it."""
from pathlib import Path
import os

class SingleInstance:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.file=open(path,'a+b'); self.file.seek(0)
        if self.file.read(1)==b'': self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close(); raise ValueError('Vivi is already running from this folder. Stop the other copy first.') from None
    def close(self):
        if self.file.closed: return
        if os.name=='nt':
            import msvcrt
            self.file.seek(0); msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
        self.file.close()
