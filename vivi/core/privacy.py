"""Opt-in, server-scoped retention for operational metadata, not moderation evidence."""
import datetime as dt
import time

RETENTION={
    'retention_history_days':'Configuration change log',
    'retention_privacy_days':'Completed or declined privacy requests',
    'retention_ticket_events_days':'Closed-ticket activity events',
}

def cleanup(store,now=None):
    now=time.time() if now is None else now
    counts=dict(history=0,privacy=0,ticket_events=0)
    guilds=[row[0] for row in store.db.execute("SELECT DISTINCT guild FROM options WHERE key LIKE 'retention_%' AND guild>0")]
    with store.db:
        for gid in guilds:
            def days(key):
                value=store.option(gid,key,0)
                return value if type(value) is int and 7<=value<=3650 else 0
            period=days('retention_history_days')
            if period:
                cutoff=dt.datetime.fromtimestamp(now-period*86400,dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                counts['history']+=store.db.execute('DELETE FROM config_history WHERE guild=? AND created<?',(gid,cutoff)).rowcount
            period=days('retention_ticket_events_days')
            if period:
                counts['ticket_events']+=store.db.execute('DELETE FROM ticket_events WHERE guild=? AND at<? AND NOT EXISTS (SELECT 1 FROM tickets t WHERE t.guild=ticket_events.guild AND t.channel=ticket_events.channel)',(gid,now-period*86400)).rowcount
            period=days('retention_privacy_days')
            if period:
                for row in store.records(gid,'privacy'):
                    data=row['data'];resolved=data.get('resolved_at')
                    if data.get('status') in {'completed','accepted','declined'} and type(resolved) in (int,float) and 0<resolved<now-period*86400:
                        counts['privacy']+=store.db.execute('DELETE FROM records WHERE guild=? AND id=? AND kind=\'privacy\'',(gid,row['id'])).rowcount
    return counts
