"""Render production editor HTML against a temporary, offline service."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from vivi.core.storage import Store
from vivi.site.dashboard import Dashboard
with tempfile.TemporaryDirectory() as temporary:
    store=Store(Path(temporary)/'vivi.sqlite3')
    guild=NS(text_channels=[],name='UI test')
    service=NS(store=store,bot=NS(get_guild=lambda gid:guild))
    dashboard=Dashboard(service);session=dict(user_id=7,csrf='sample-token')
    content='<details><summary>First panel</summary><p>One</p><form id="sample-upload"><label>File <input type="file" name="file"></label><button>Upload</button></form></details><details><summary>Second panel</summary><p>Two</p></details>'+dashboard.studio_forms(1,session)
    print(dashboard.page(dashboard.personalize(content,1,session)).text)
    store.close()
