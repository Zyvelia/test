"""Small persistent store. Only the bot process should open this database."""
import sqlite3
from pathlib import Path

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
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
        """)

    def settings(self, guild):
        return self.db.execute('SELECT * FROM settings WHERE guild=?', (guild,)).fetchone()

    def configure(self, guild, welcome, category, staff, logs):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?,?,?,?)',
                            (guild, welcome, category, staff, logs))

    def add_role(self, guild, role):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO roles VALUES (?,?)', (guild, role))

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
