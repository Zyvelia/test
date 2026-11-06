"""Optional Windows tray launcher. Native UI imports are lazy for Linux/headless use."""
import logging
import os
from pathlib import Path
import subprocess
import webbrowser
from urllib.parse import urlsplit
from .runtime import SingleInstance

ROOT=Path(__file__).resolve().parents[1]

class TrayController:
    def __init__(self,root=ROOT): self.root=Path(root);self.process=None
    def owned(self): return self.process is not None and self.process.poll() is None
    def running(self):
        if self.owned(): return True
        try: instance=SingleInstance(self.root/'data'/'vivi.lock')
        except ValueError: return True
        instance.close();return False
    def start(self):
        if self.running(): return False
        executable=self.root/'.venv'/'Scripts'/'python.exe'
        if not executable.exists(): raise ValueError('Run setup.bat first.')
        self.process=subprocess.Popen([str(executable),'-u','-m','vivi.supervisor'],cwd=self.root,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return True
    def stop(self):
        # Only terminate a process tree launched by this tray, never a PID read from a file.
        if not self.owned(): return False
        if os.name=='nt': subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],check=True,capture_output=True)
        else: self.process.terminate()
        self.process.wait(timeout=10);self.process=None;return True
    def dashboard(self):
        from dotenv import load_dotenv
        load_dotenv(self.root/'.env')
        parsed=urlsplit(os.getenv('DASHBOARD_REDIRECT_URI','http://127.0.0.1:8765/callback'))
        if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost'}: raise ValueError('Dashboard must use a local loopback URL.')
        webbrowser.open(f'http://{parsed.hostname}:{parsed.port or 80}/')


def main():
    if os.name!='nt': raise SystemExit('The native tray is for Windows. Linux can use systemd and the web health dashboard.')
    try: import pystray
    except ImportError: raise SystemExit('Run setup.bat to install Windows tray support.')
    from PIL import Image,ImageDraw,ImageFont
    folder=ROOT/'data'/'logs';folder.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=folder/'tray.log',level=logging.INFO)
    controller=TrayController()
    image=Image.new('RGBA',(64,64),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.ellipse((1,1,62,62),fill='#9678dd');draw.text((18,8),'V',font=ImageFont.load_default(size=42),fill='white')
    def safe(function):
        def action(icon,item):
            try: function()
            except Exception as error:
                logging.error('Tray action failed: %s',type(error).__name__)
                if getattr(icon,'HAS_NOTIFICATION',False): icon.notify('Action failed. Open Vivi logs for details.','Vivi')
            icon.update_menu()
        return action
    def logs(): os.startfile(str(folder))
    def exit_tray(icon,item):
        try:
            if controller.owned(): controller.stop()
        except Exception as error: logging.error('Tray stop failed: %s',type(error).__name__)
        finally: icon.stop()
    menu=pystray.Menu(
        pystray.MenuItem(lambda item:'Vivi: '+('running (tray)' if controller.owned() else 'running elsewhere' if controller.running() else 'stopped'),None,enabled=False),
        pystray.MenuItem('Start Vivi',safe(controller.start),enabled=lambda item:not controller.running()),
        pystray.MenuItem('Stop Vivi (started by this tray)',safe(controller.stop),enabled=lambda item:controller.owned()),
        pystray.MenuItem('Open dashboard',safe(controller.dashboard)),
        pystray.MenuItem('Open logs',safe(logs)),
        pystray.MenuItem('Exit tray (stop its Vivi process)',exit_tray))
    pystray.Icon('Vivi',image,'Vivi controls',menu).run()

if __name__=='__main__': main()
