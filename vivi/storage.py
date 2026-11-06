"""Small persistent store. Only the bot process should open this database."""
import sqlite3
import json
import time
import secrets
import hashlib
import hmac
from contextvars import ContextVar
from pathlib import Path

class Store:
    def __init__(self, path):
        self.path=Path(path)
        self.actor=ContextVar('vivi_config_actor',default='system')
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS config_history (id INTEGER PRIMARY KEY, guild INTEGER, actor TEXT, action TEXT, before_json TEXT, after_json TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS settings (
                guild INTEGER PRIMARY KEY, welcome INTEGER NOT NULL,
                category INTEGER NOT NULL, staff INTEGER NOT NULL, logs INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS roles (guild INTEGER, role INTEGER, PRIMARY KEY(guild, role));
            CREATE TABLE IF NOT EXISTS tickets (
                guild INTEGER, user INTEGER, channel INTEGER UNIQUE,
                PRIMARY KEY(guild, user));
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY, guild INTEGER, user INTEGER,
                moderator INTEGER, reason TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS options (guild INTEGER, key TEXT, value TEXT, PRIMARY KEY(guild,key));
            CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, guild INTEGER, kind TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS ballots (item TEXT, voter TEXT, value INTEGER, PRIMARY KEY(item,voter));
            CREATE TABLE IF NOT EXISTS profiles (guild INTEGER, user INTEGER, data TEXT, PRIMARY KEY(guild,user));
            CREATE TABLE IF NOT EXISTS cases (id INTEGER PRIMARY KEY, guild INTEGER, user INTEGER,
                moderator INTEGER, action TEXT, reason TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        if not self.option(0,'internal_legacy_cases',False):
            with self.db:
                self.db.execute("INSERT INTO cases(guild,user,moderator,action,reason,created) SELECT guild,user,moderator,'legacy warning',reason,created FROM warnings")
                self.db.execute('INSERT INTO options VALUES (?,?,?)',(0,'internal_legacy_cases','true'))

    def settings(self, guild):
        return self.db.execute('SELECT * FROM settings WHERE guild=?', (guild,)).fetchone()

    def configure(self, guild, welcome, category, staff, logs):
        before=self.export_config(guild)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?,?,?,?)',
                            (guild, welcome, category, staff, logs))
            self.log_config(guild,'server setup',before)

    def add_role(self, guild, role):
        before=self.export_config(guild)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO roles VALUES (?,?)', (guild, role))
            self.log_config(guild,'role button registration',before)

    def roles(self):
        return self.db.execute('SELECT guild, role FROM roles').fetchall()

    def ticket_for_user(self, guild, user):
        return self.db.execute('SELECT * FROM tickets WHERE guild=? AND user=?', (guild,user)).fetchone()

    def ticket_for_channel(self, channel):
        return self.db.execute('SELECT * FROM tickets WHERE channel=?', (channel,)).fetchone()

    def add_ticket(self, guild, user, channel):
        with self.db:
            self.db.execute('INSERT INTO tickets VALUES (?,?,?)', (guild,user,channel))

    def remove_ticket(self, channel):
        with self.db:
            self.db.execute('DELETE FROM tickets WHERE channel=?', (channel,))

    def warn(self, guild, user, moderator, reason):
        with self.db:
            cur=self.db.execute('INSERT INTO warnings(guild,user,moderator,reason) VALUES (?,?,?,?)',
                                (guild,user,moderator,reason))
        return cur.lastrowid

    def warnings(self, guild, user):
        return self.db.execute('SELECT * FROM warnings WHERE guild=? AND user=? ORDER BY id DESC LIMIT 10',
                               (guild,user)).fetchall()

    def close(self):
        self.db.close()

    def option(self, guild, key, default=None):
        row = self.db.execute('SELECT value FROM options WHERE guild=? AND key=?', (guild,key)).fetchone()
        return json.loads(row[0]) if row else default

    def set_option(self, guild, key, value):
        before=self.export_config(guild) if guild and not key.startswith('internal_') else None
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO options VALUES (?,?,?)', (guild,key,json.dumps(value)))
            if before is not None: self.log_config(guild,'setting: '+key,before)

    def record(self, ident):
        row = self.db.execute('SELECT * FROM records WHERE id=?', (ident,)).fetchone()
        return dict(row, data=json.loads(row['data'])) if row else None

    def records(self, guild=None, kind=None):
        sql, args = 'SELECT * FROM records WHERE 1=1', []
        if guild is not None: sql += ' AND guild=?'; args.append(guild)
        if kind is not None: sql += ' AND kind=?'; args.append(kind)
        return [dict(row, data=json.loads(row['data'])) for row in self.db.execute(sql,args)]

    def put_record(self, guild, kind, data, ident=None):
        ident = ident or secrets.token_hex(8)
        before=self.export_config(guild) if kind=='notification' else None
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (ident,guild,kind,json.dumps(data)))
            if before is not None: self.log_config(guild,'notification subscription',before)
        return ident

    def delete_record(self, ident):
        record=self.record(ident)
        guild=record['guild'] if record else 0
        before=self.export_config(guild) if record and record['kind']=='notification' else None
        with self.db:
            self.db.execute('DELETE FROM records WHERE id=?', (ident,))
            self.db.execute('DELETE FROM ballots WHERE item=?', (ident,))
            if before is not None: self.log_config(guild,'remove notification subscription',before)

    def vote(self, item, voter, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO ballots VALUES (?,?,?)', (item,str(voter),value))

    def votes(self, item):
        return self.db.execute('SELECT voter,value FROM ballots WHERE item=?', (item,)).fetchall()

    def profile(self, guild, user):
        row = self.db.execute('SELECT data FROM profiles WHERE guild=? AND user=?', (guild,user)).fetchone()
        base = dict(xp=0, coins=0, visible=True, birthday='', timezone='UTC', spotlight=False,
                    achievements=[], owned=[], equipped='', memory=False, turns=[], last_xp=0, last_hash='')
        if row: base.update(json.loads(row[0]))
        return base

    def save_profile(self, guild, user, data):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO profiles VALUES (?,?,?)', (guild,user,json.dumps(data)))

    def profiles(self, guild):
        return [(row['user'], self.profile(guild,row['user'])) for row in
                self.db.execute('SELECT user FROM profiles WHERE guild=?', (guild,))]

    def add_case(self, guild, user, moderator, action, reason):
        with self.db:
            cur = self.db.execute('INSERT INTO cases(guild,user,moderator,action,reason) VALUES (?,?,?,?,?)',
                                  (guild,user,moderator,action,reason))
        return cur.lastrowid

    def search_cases(self, guild, user=None, query=''):
        sql, args = 'SELECT * FROM cases WHERE guild=?', [guild]
        if user is not None: sql += ' AND user=?'; args.append(user)
        if query: sql += ' AND instr(lower(reason),lower(?))>0'; args.append(query)
        return self.db.execute(sql+' ORDER BY id DESC LIMIT 15',args).fetchall()

    def export_config(self, guild):
        config = self.settings(guild)
        return {'version':2,'guild':guild,'settings':dict(config) if config else None,
                'options':{r['key']:json.loads(r['value']) for r in
                           self.db.execute("SELECT key,value FROM options WHERE guild=? AND key NOT LIKE 'internal_%'",(guild,))},
                'roles':[r['role'] for r in self.db.execute('SELECT role FROM roles WHERE guild=?',(guild,))],
                'subscriptions':[{k:r['data'][k] for k in ['provider','source','channel']} for r in self.records(guild,'notification')]}

    def restore_config(self, guild, backup):
        # Validation happens before the transaction; personal data and records are never restored.
        from .features import validate_backup
        validate_backup(guild, backup)
        before=self.export_config(guild)
        with self.db:
            self.db.execute("DELETE FROM options WHERE guild=? AND key NOT LIKE 'internal_%'",(guild,))
            for key,value in backup['options'].items():
                self.db.execute('INSERT INTO options VALUES (?,?,?)',(guild,key,json.dumps(value)))
            self.db.execute('DELETE FROM roles WHERE guild=?',(guild,))
            for role in backup['roles']:
                self.db.execute('INSERT OR IGNORE INTO roles VALUES (?,?)',(guild,role))
            self.db.execute('DELETE FROM settings WHERE guild=?',(guild,))
            self.db.execute("DELETE FROM records WHERE guild=? AND kind='notification'",(guild,))
            from .operations import subscription
            for item in backup.get('subscriptions',[]):
                data=subscription(item['provider'],item['source'],item['channel'])
                self.db.execute('INSERT INTO records VALUES (?,?,?,?)',(secrets.token_hex(8),guild,'notification',json.dumps(data)))
            s=backup['settings']
            if s:
                self.db.execute('INSERT INTO settings VALUES (?,?,?,?,?)',
                                (guild,s['welcome'],s['category'],s['staff'],s['logs']))
            self.log_config(guild,'restore',before)

    def delete_personal(self, guild, user):
        # Remove attributable ballots, including the keyed voter hash for open anonymous polls.
        with self.db:
            for record in self.records(guild,'poll'):
                data=record['data']
                if data.get('anonymous') and data.get('salt'):
                    voter=hmac.new(bytes.fromhex(data['salt']),str(user).encode(),hashlib.sha256).hexdigest()
                    self.db.execute('DELETE FROM ballots WHERE item=? AND voter=?',(record['id'],voter))
            self.db.execute('DELETE FROM profiles WHERE guild=? AND user=?',(guild,user))
            self.db.execute('DELETE FROM ballots WHERE voter=? AND item IN (SELECT id FROM records WHERE guild=?)',
                            (str(user),guild))

    def erase_moderation(self, guild, user):
        with self.db:
            self.db.execute('DELETE FROM warnings WHERE guild=? AND user=?',(guild,user))
            self.db.execute('DELETE FROM cases WHERE guild=? AND user=?',(guild,user))
            self.db.execute('UPDATE cases SET moderator=0 WHERE guild=? AND moderator=?',(guild,user))
            self.db.execute('UPDATE warnings SET moderator=0 WHERE guild=? AND moderator=?',(guild,user))

    def log_config(self,guild,action,before):
        if not guild: return
        after=self.export_config(guild)
        if before==after and action!='restore': return
        self.db.execute('INSERT INTO config_history(guild,actor,action,before_json,after_json) VALUES (?,?,?,?,?)',
            (guild,str(self.actor.get())[:100],action[:100],json.dumps(before),json.dumps(after)))
        self.db.execute('DELETE FROM config_history WHERE guild=? AND id NOT IN (SELECT id FROM config_history WHERE guild=? ORDER BY id DESC LIMIT 100)',(guild,guild))

    def history(self,guild):
        return self.db.execute('SELECT id,actor,action,created FROM config_history WHERE guild=? ORDER BY id DESC LIMIT 100',(guild,)).fetchall()

    def revision(self,guild,ident):
        row=self.db.execute('SELECT * FROM config_history WHERE guild=? AND id=?',(guild,ident)).fetchone()
        return dict(row,before=json.loads(row['before_json']),after=json.loads(row['after_json'])) if row else None


def database_path(root):
    """Keep existing installations on their database; new ones use the Vivi name."""
    legacy=Path(root)/'data'/'aurora.sqlite3'
    current=Path(root)/'data'/'vivi.sqlite3'
    if legacy.exists() and current.exists():
        raise ValueError('Both legacy and Vivi databases exist. Back them up and select one before starting.')
    return legacy if legacy.exists() else current
