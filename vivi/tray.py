"""Optional Windows tray launcher. Native UI imports are lazy for Linux/headless use."""
import logging
import os
from pathlib import Path
import subprocess
import threading
import webbrowser
from urllib.parse import urlsplit
from .runtime import SingleInstance

ROOT=Path(__file__).resolve().parents[1]

class TrayController:
    def __init__(self,root=ROOT):
        self.root=Path(root);self.process=None;self.updating=False;self.last_update='';self._actions=threading.RLock();self.update_thread=None
    def owned(self): return self.process is not None and self.process.poll() is None
    def running(self):
        if self.owned(): return True
        try: instance=SingleInstance(self.root/'data'/'vivi.lock')
        except ValueError: return True
        instance.close();return False
    def start(self):
        with self._actions:
            if self.updating:raise ValueError('An update is running. Please wait.')
            return self._start()
    def _start(self,after_update=False):
        if self.running(): return False
        executable=self.root/'.venv'/'Scripts'/'python.exe'
        if not executable.exists(): raise ValueError('Run setup.bat first.')
        self.process=subprocess.Popen([str(executable),'-u','-m','vivi.supervisor'],cwd=self.root,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
            env={**os.environ,'AUTO_UPDATE':'false'} if after_update else None)
        return True
    def stop(self):
        with self._actions:
            if self.updating:raise ValueError('An update is running. Please wait.')
            return self._stop()
    def _stop(self):
        # Only terminate a process tree launched by this tray, never a PID read from a file.
        if not self.owned(): return False
        if os.name=='nt': subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],check=True,capture_output=True)
        else: self.process.terminate()
        self.process.wait(timeout=10);self.process=None;return True
    def begin_update(self,finished=None):
        """Claim the update before spawning a worker so repeated clicks cannot race."""
        with self._actions:
            if self.updating:raise ValueError('An update is already running.')
            if self.running() and not self.owned():raise ValueError('Vivi is running outside this tray. Stop its launcher or startup service before updating.')
            executable=self.root/'.venv'/'Scripts'/'python.exe'
            if not executable.is_file():raise ValueError('Run setup.bat first.')
            if not (self.root/'vivi'/'updater.py').is_file():raise ValueError('Install the updater once using the update guide first.')
            self.updating=True;self.last_update='Updating from GitHub…'
            self.update_thread=threading.Thread(target=self._update_worker,args=(finished,),name='vivi-tray-update',daemon=False)
            try:self.update_thread.start()
            except Exception:self.updating=False;raise
    def _update_worker(self,finished):
        success=False;restart=self.owned();folder=self.root/'data'/'logs'
        try:
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/'update.log'
            if path.exists() and path.stat().st_size>2_000_000:
                previous=folder/'update.previous.log';previous.unlink(missing_ok=True);path.replace(previous)
            with path.open('a',encoding='utf-8') as log:
                log.write('\nVivi tray update started.\n');log.flush()
                if restart:self._stop()
                if self.running():raise ValueError('Another Vivi process is running. Stop it before updating.')
                result=subprocess.run([str(self.root/'.venv'/'Scripts'/'python.exe'),'-u','-m','vivi.updater'],cwd=self.root,
                    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:raise ValueError('Update failed. Vivi remains stopped; open update.log for the result.')
                if restart:
                    if not self._start(after_update=True):raise ValueError('Updated, but another Vivi instance started. Check its status before restarting.')
                    self.last_update='Update complete. Vivi is starting.'
                else:self.last_update='Update complete. Vivi remains stopped.'
                log.write(self.last_update+'\n');success=True
        except Exception as error:
            self.last_update=str(error)
            logging.error('Tray update failed: %s',type(error).__name__)
            try:
                with (folder/'update.log').open('a',encoding='utf-8') as log:log.write('Tray update stopped: '+str(error)+'\n')
            except OSError:pass
        finally:
            with self._actions:self.updating=False
            if finished:
                try:finished(success,self.last_update)
                except Exception:logging.exception('Tray update notification failed')
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
                if getattr(icon,'HAS_NOTIFICATION',False): icon.notify(str(error)[:240],'Vivi')
            icon.update_menu()
        return action
    def logs(): os.startfile(str(folder))
    def update_log():
        path=folder/'update.log';path.touch(exist_ok=True);os.startfile(str(path))
    def update(icon,item):
        def finished(success,message):
            if getattr(icon,'HAS_NOTIFICATION',False):icon.notify(message[:240],'Vivi update')
            icon.update_menu()
        try:
            controller.begin_update(finished)
            if controller.updating and getattr(icon,'HAS_NOTIFICATION',False):icon.notify('Updating from GitHub. Progress is in data/logs/update.log.','Vivi update')
        except Exception as error:
            logging.error('Tray update could not start: %s',type(error).__name__)
            if getattr(icon,'HAS_NOTIFICATION',False):icon.notify(str(error)[:240],'Vivi update')
        icon.update_menu()
    def exit_tray(icon,item):
        if controller.updating:
            if getattr(icon,'HAS_NOTIFICATION',False):icon.notify('Wait for the update to finish before closing the tray.','Vivi')
            return
        try:
            if controller.owned(): controller.stop()
        except Exception as error: logging.error('Tray stop failed: %s',type(error).__name__)
        finally: icon.stop()
    menu=pystray.Menu(
        pystray.MenuItem(lambda item:'Vivi: '+('updating…' if controller.updating else 'running (tray)' if controller.owned() else 'running elsewhere' if controller.running() else 'stopped'),None,enabled=False),
        pystray.MenuItem('Start Vivi',safe(controller.start),enabled=lambda item:not controller.updating and not controller.running()),
        pystray.MenuItem('Stop Vivi (started by this tray)',safe(controller.stop),enabled=lambda item:not controller.updating and controller.owned()),
        pystray.MenuItem('Update Vivi from GitHub',update,enabled=lambda item:not controller.updating),
        pystray.MenuItem(lambda item:controller.last_update or 'No update run this session',None,enabled=False),
        pystray.MenuItem('Open dashboard',safe(controller.dashboard)),
        pystray.MenuItem('Open logs',safe(logs)),
        pystray.MenuItem('Open update log',safe(update_log)),
        pystray.MenuItem('Exit tray (stop its Vivi process)',exit_tray,enabled=lambda item:not controller.updating))
    pystray.Icon('Vivi',image,'Vivi controls',menu).run()

if __name__=='__main__': main()
