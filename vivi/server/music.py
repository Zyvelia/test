"""Uploaded-audio playback and optional temporary voice rooms."""
import asyncio
import contextlib
import logging
import os
from pathlib import Path
import secrets
import shutil
import time

import discord
from discord import app_commands
from vivi.bot import ROOT, reply
from vivi.core.features import enabled

LOG=logging.getLogger('vivi.server.music')
FORMATS={'.mp3':'mp3','.wav':'wav','.ogg':'ogg','.opus':'ogg','.flac':'flac','.m4a':'mov'}
MAX_BYTES=10*1024*1024

class VoiceTools:
    def __init__(self,service):
        self.service=service; self.bot=service.bot; self.store=service.store
        self.queues={}; self.active={}; self.locks={}; self.loop=None; self.closing=False; self.pending_delete=set()
        self.bot.add_listener(self.voice_state,'on_voice_state_update')

    def remove_file(self,path):
        try: Path(path).unlink(missing_ok=True); self.pending_delete.discard(str(path))
        except OSError: self.pending_delete.add(str(path))

    def lock(self,guild): return self.locks.setdefault(guild,asyncio.Lock())

    async def actor_channel(self,i,require_bot=False):
        channel=i.user.voice.channel if i.user.voice else None
        if not isinstance(channel,discord.VoiceChannel): raise ValueError('Join a regular voice channel first.')
        client=i.guild.voice_client
        if client and client.channel.id!=channel.id: raise ValueError('Join the voice channel Vivi is already using.')
        if require_bot and (not client or not client.is_connected()): raise ValueError('Vivi is not connected to voice.')
        return channel,client

    def ffmpeg(self):
        command=os.getenv('FFMPEG_PATH','ffmpeg')
        found=shutil.which(command)
        if not found: raise ValueError('Install FFmpeg on the host PC or set FFMPEG_PATH to ffmpeg.exe, then restart Vivi.')
        return found

    async def enqueue(self,i,attachment):
        extension=Path(attachment.filename).suffix.lower()
        if extension not in FORMATS or attachment.size<=0 or attachment.size>MAX_BYTES:
            raise ValueError('Upload an MP3, WAV, OGG, Opus, FLAC or M4A file under 10 MiB.')
        self.ffmpeg()
        self.loop=asyncio.get_running_loop()
        async with self.lock(i.guild_id):
            channel,client=await self.actor_channel(i)
            queue=self.queues.setdefault(i.guild_id,[])
            if len(queue)>=10: raise ValueError('The queue is full (10 waiting tracks).')
            # Only Discord attachments are accepted. Never pass a member-supplied URL to FFmpeg.
            data=await attachment.read()
            if len(data)>MAX_BYTES: raise ValueError('Audio exceeds the size limit.')
            folder=ROOT/'data'/'audio'; folder.mkdir(parents=True,exist_ok=True)
            path=folder/(secrets.token_hex(16)+extension); path.write_bytes(data)
            if not client:
                try: client=await channel.connect(timeout=20,reconnect=True)
                except Exception: path.unlink(missing_ok=True); raise
            queue.append(dict(path=str(path),title=attachment.filename[:100],requester=i.user.id,format=FORMATS[extension]))
            if i.guild_id not in self.active: await self._next(i.guild)

    async def _next(self,guild):
        previous=self.active.pop(guild.id,None)
        if previous: self.remove_file(previous['path'])
        queue=self.queues.setdefault(guild.id,[])
        client=guild.voice_client
        if self.closing or not enabled(self.store,guild.id,'music') or not client or not client.is_connected():
            for track in queue: self.remove_file(track['path'])
            queue.clear(); return
        if not queue: return
        track=queue.pop(0); self.active[guild.id]=track
        try:
            source=discord.FFmpegPCMAudio(track['path'],executable=self.ffmpeg(),
                before_options=f'-nostdin -protocol_whitelist file,pipe -f {track["format"]}',options='-vn')
            audio=discord.PCMVolumeTransformer(source,volume=.5)
            def finished(error):
                if error: LOG.warning('Audio playback failed (%s)',type(error).__name__)
                if self.loop and not self.loop.is_closed() and not self.closing:
                    future=asyncio.run_coroutine_threadsafe(self.advance(guild,track["path"]),self.loop)
                    def check(result):
                        try: result.result()
                        except Exception: LOG.exception('Could not advance audio queue')
                    future.add_done_callback(check)
            try: client.play(audio,after=finished)
            except Exception: audio.cleanup(); raise
        except Exception:
            self.active.pop(guild.id,None); self.remove_file(track['path'])
            LOG.exception('Could not start uploaded audio')
            raise

    async def advance(self,guild,expected=None):
        async with self.lock(guild.id):
            if expected is not None and (self.active.get(guild.id) or {}).get('path')!=expected: return
            await self._next(guild)

    async def stop(self,guild,disconnect=False):
        async with self.lock(guild.id):
            for track in self.queues.pop(guild.id,[]): self.remove_file(track['path'])
            client=guild.voice_client
            if client: client.stop()
            track=self.active.pop(guild.id,None)
            if track: self.remove_file(track['path'])
            if disconnect and client: await client.disconnect(force=True)

    async def close(self):
        self.closing=True
        for guild in self.bot.guilds:
            with contextlib.suppress(Exception): await self.stop(guild,True)

    async def voice_state(self,member,before,after):
        # Stop music when the last human leaves, including a host disconnect.
        if before.channel and member.guild.voice_client and member.guild.voice_client.channel==before.channel:
            if not any(not m.bot for m in before.channel.members): await self.stop(member.guild,True)
        for record in self.store.records(member.guild.id,'voice_room'):
            channel=member.guild.get_channel(record['data']['channel'])
            if channel and not channel.members and time.time()-record['data'].get('created',0)>=10:
                try: await channel.delete(reason='Vivi empty temporary voice room')
                except discord.HTTPException: continue
                self.store.delete_record(record['id'])
        if member.bot or not after.channel or (before.channel and before.channel.id==after.channel.id): return
        guild=member.guild
        if not enabled(self.store,guild.id,'voice_rooms') or after.channel.id!=self.store.option(guild.id,'voice_lobby',0): return
        async with self.lock(guild.id):
            if len(self.store.records(guild.id,'voice_room'))>=25: return
            category=guild.get_channel(self.store.option(guild.id,'voice_category',0))
            if not isinstance(category,discord.CategoryChannel): return
            channel=None
            try:
                # Retain category restrictions; owner controls are mediated by commands, not Manage Channels.
                overwrites=dict(category.overwrites)
                ow=overwrites.get(member,discord.PermissionOverwrite()); ow.view_channel=True; ow.connect=True
                overwrites[member]=ow
                bot_ow=overwrites.get(guild.me,discord.PermissionOverwrite()); bot_ow.view_channel=True; bot_ow.connect=True; bot_ow.manage_channels=True
                overwrites[guild.me]=bot_ow
                channel=await guild.create_voice_channel(f'{member.display_name[:65]}’s room',category=category,
                    user_limit=self.store.option(guild.id,'voice_user_limit',0),overwrites=overwrites,reason='Vivi temporary voice room')
                self.store.put_record(guild.id,'voice_room',dict(channel=channel.id,owner=member.id,created=time.time(),previous_connect=category.overwrites_for(guild.default_role).connect),f'voice:{channel.id}')
                await member.move_to(channel,reason='Vivi join-to-create voice room')
            except discord.HTTPException:
                LOG.warning('Temporary voice room failed in guild %s',guild.id)
                if channel:
                    with contextlib.suppress(discord.HTTPException): await channel.delete(reason='Vivi incomplete room cleanup')
                    if guild.get_channel(channel.id) is None: self.store.delete_record(f'voice:{channel.id}')

    async def maintenance(self):
        for path in list(self.pending_delete): self.remove_file(path)
        folder=ROOT/'data'/'audio'
        if folder.exists():
            in_use={x['path'] for x in self.active.values()} | {x['path'] for q in self.queues.values() for x in q}
            for path in folder.iterdir():
                if path.is_file() and str(path) not in in_use and time.time()-path.stat().st_mtime>3600: self.remove_file(path)
        for record in self.store.records(kind='voice_room'):
            guild=self.bot.get_guild(record['guild'])
            if not guild: continue
            channel=guild.get_channel(record['data']['channel'])
            if channel is None: self.store.delete_record(record['id']); continue
            if not channel.members and time.time()-record['data'].get('created',0)>=10:
                try: await channel.delete(reason='Vivi empty temporary voice room cleanup')
                except discord.HTTPException: continue
                self.store.delete_record(record['id'])
        for guild in self.bot.guilds:
            if guild.voice_client and (not enabled(self.store,guild.id,'music') or not any(not m.bot for m in guild.voice_client.channel.members)):
                await self.stop(guild,True)


def register_voice(bot):
    service=bot.community; voice=service.voice
    music=app_commands.Group(name='music',description='Uploaded-audio queue and playback',guild_only=True)
    rooms=app_commands.Group(name='room',description='Your temporary voice room controls',guild_only=True)

    @music.command(name='play',description='Queue an uploaded audio attachment (under 10 MiB). Join voice first.')
    @app_commands.checks.cooldown(1,10,key=lambda i:(i.guild_id,i.user.id))
    async def play(i:discord.Interaction,file:discord.Attachment):
        if not await service.need(i,'music'): return
        await i.response.defer(ephemeral=True)
        await voice.enqueue(i,file)
        await reply(i,'Audio queued. Playback uses uploaded files, not YouTube/Spotify links.')

    @music.command(name='queue',description='Show the current track and queued uploads.')
    async def queue(i:discord.Interaction):
        if not await service.need(i,'music'): return
        active=voice.active.get(i.guild_id)
        lines=['Now: '+(active['title'] if active else 'nothing')]+[f'{n}. {t["title"]}' for n,t in enumerate(voice.queues.get(i.guild_id,[]),1)]
        await reply(i,'\n'.join(lines))

    @music.command(name='pause',description='Pause playback in your current voice channel.')
    async def pause(i:discord.Interaction):
        if not await service.need(i,'music'): return
        _,client=await voice.actor_channel(i,True); client.pause(); await reply(i,'Paused.')

    @music.command(name='resume',description='Resume paused audio in your current voice channel.')
    async def resume(i:discord.Interaction):
        if not await service.need(i,'music'): return
        _,client=await voice.actor_channel(i,True); client.resume(); await reply(i,'Resumed.')

    @music.command(name='skip',description='Skip the current uploaded track in your voice channel.')
    async def skip(i:discord.Interaction):
        if not await service.need(i,'music'): return
        _,client=await voice.actor_channel(i,True); client.stop(); await reply(i,'Skipped.')

    @music.command(name='stop',description='Clear the audio queue and stop playback in your voice channel.')
    async def stop(i:discord.Interaction):
        if not await service.need(i,'music'): return
        await voice.actor_channel(i,True); await voice.stop(i.guild); await reply(i,'Playback stopped; queue cleared.')

    @music.command(name='leave',description='Clear playback and disconnect Vivi from your voice channel.')
    async def leave(i:discord.Interaction):
        await voice.actor_channel(i,True); await i.response.defer(ephemeral=True)
        await voice.stop(i.guild,True); await reply(i,'Disconnected.')

    @music.command(name='volume',description='Set playback volume from 0 to 100 percent.')
    async def volume(i:discord.Interaction,percent:app_commands.Range[int,0,100]):
        if not await service.need(i,'music'): return
        _,client=await voice.actor_channel(i,True)
        if not isinstance(client.source,discord.PCMVolumeTransformer): return await reply(i,'Nothing is playing.')
        client.source.volume=percent/100; await reply(i,f'Volume: {percent}%.')

    async def owned(i):
        if not await service.need(i,'voice_rooms'): return None
        channel=i.user.voice.channel if i.user.voice else None
        record=service.store.record(f'voice:{channel.id}') if channel else None
        if not record or record['guild']!=i.guild_id or (record['data']['owner']!=i.user.id and not i.user.guild_permissions.manage_channels):
            await reply(i,'Join a Vivi-created room you own, or use Manage Channels permission.'); return None
        return channel

    @rooms.command(name='rename',description='Rename your temporary voice room.')
    async def rename(i:discord.Interaction,name:app_commands.Range[str,1,80]):
        channel=await owned(i)
        if not channel: return
        await i.response.defer(ephemeral=True); await channel.edit(name=name,reason='Vivi room owner rename'); await reply(i,'Room renamed.')

    @rooms.command(name='limit',description='Set your temporary room’s member limit; 0 means no limit.')
    async def limit(i:discord.Interaction,members:app_commands.Range[int,0,99]):
        channel=await owned(i)
        if not channel: return
        await i.response.defer(ephemeral=True); await channel.edit(user_limit=members,reason='Vivi room owner limit'); await reply(i,'Member limit updated.')

    @rooms.command(name='lock',description='Deny new @everyone connections to your room, or remove that deny.')
    async def lock(i:discord.Interaction,locked:bool):
        channel=await owned(i)
        if not channel: return
        await i.response.defer(ephemeral=True)
        ow=channel.overwrites_for(i.guild.default_role); record=service.store.record(f'voice:{channel.id}'); ow.connect=False if locked else record['data'].get('previous_connect')
        await channel.set_permissions(i.guild.default_role,overwrite=ow,reason='Vivi room owner lock control')
        await reply(i,'Room locked for @everyone. Explicit role/member allows may still connect.' if locked else 'Room @everyone connect deny removed; category/role permissions still apply.')

    bot.tree.add_command(music); bot.tree.add_command(rooms)
