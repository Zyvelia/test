"""Opt-in Windows logon tasks and Linux systemd user services."""
import os
import platform
import shutil
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def quote(value): return "'"+str(value).replace("'","''")+"'"

def script(root,remove=False):
    root=Path(root).resolve(); executable=root/'.venv'/'Scripts'/'pythonw.exe'
    prefix="$ErrorActionPreference='Stop'; $user=[Security.Principal.WindowsIdentity]::GetCurrent(); $name='ViviBot-'+$user.User.Value; "
    if remove:
        return prefix+"$task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue; if($task){Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $name -Confirm:$false}; Write-Output 'Vivi automatic startup removed.'"
    return prefix+f"$action=New-ScheduledTaskAction -Execute {quote(executable)} -Argument '-u -m vivi.supervisor' -WorkingDirectory {quote(root)}; "+\
        "$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user.Name; "+\
        "$principal=New-ScheduledTaskPrincipal -UserId $user.Name -LogonType Interactive -RunLevel Limited; "+\
        "$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero); "+\
        "Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null; Write-Output 'Vivi will start in the background when this Windows user signs in. Keep this folder in the same location.'"

def systemd_unit(root):
    root=Path(root).resolve()
    def escape(value):
        value=str(value)
        if any(x in value for x in ['\n','\r','\x00']): raise ValueError('Unsupported newline in installation path.')
        return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
    return ('[Unit]\nDescription=Vivi Discord Bot\n\n[Service]\nType=simple\n'
            'WorkingDirectory='+str(root).replace('%','%%')+'\nExecStart='+escape(root/'.venv/bin/python')+' -u -m vivi.supervisor\n'
            'Restart=on-failure\nRestartSec=10\nKillMode=control-group\nTimeoutStopSec=15\n'
            'Environment=PYTHONUNBUFFERED=1\nUMask=0077\n\n[Install]\nWantedBy=default.target\n')

def linux_startup(root,remove=False):
    if not shutil.which('systemctl'): raise SystemExit('systemd user services are unavailable. Use start.sh directly, or your distribution’s process manager.')
    base=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))
    folder=base/'systemd/user'; unit=folder/'vivi-bot.service'
    if remove:
        if not unit.exists(): print('No Vivi user service is installed.'); return
        if unit.exists() and 'Description=Vivi Discord Bot' not in unit.read_text(): raise SystemExit('Refusing to remove an unrelated service file.')
        subprocess.run(['systemctl','--user','disable','--now','vivi-bot.service'],check=False)
        unit.unlink(missing_ok=True)
        subprocess.run(['systemctl','--user','daemon-reload'],check=True)
        print('Vivi systemd user startup removed.'); return
    if not (Path(root)/'.venv/bin/python').exists(): raise SystemExit('Run setup.sh first.')
    folder.mkdir(parents=True,exist_ok=True)
    if unit.exists() and 'Description=Vivi Discord Bot' not in unit.read_text(): raise SystemExit('Refusing to overwrite an unrelated service file.')
    unit.write_text(systemd_unit(root))
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','vivi-bot.service'],check=True)
    print('Vivi will start with your systemd user session. Run systemctl --user start vivi-bot to start now. See docs/LINUX.md for reboot/linger options.')

def main():
    remove=len(sys.argv)>1 and sys.argv[1]=='remove'
    if platform.system()=='Linux': return linux_startup(ROOT,remove)
    if os.name!='nt': raise SystemExit('Automatic startup supports Windows and Linux systemd user sessions.')
    if not remove and not (ROOT/'.venv'/'Scripts'/'pythonw.exe').exists(): raise SystemExit('Run setup.bat first.')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script(ROOT,remove)],check=False)
    raise SystemExit(result.returncode)

if __name__=='__main__': main()
