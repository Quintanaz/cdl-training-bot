"""CDL Training Hub: safe setup, intake, manual moderation, optional discovery."""
import asyncio
import json
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from catalog import CATEGORIES, FORUMS, FORUM_TAGS, TOPICS, classify, clean_url
import sources
from sources import discover
from official_watch import OfficialWatch
from pool_monitor import CandidateStore, extract_candidates, is_official
from storage import Store

ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
TOKEN=os.getenv('DISCORD_TOKEN','')
GUILD_ID=int(os.getenv('DISCORD_GUILD_ID','0'))
if not TOKEN or not GUILD_ID:
    raise RuntimeError('DISCORD_TOKEN and DISCORD_GUILD_ID must be set in .env')
MAP_FILE=ROOT/'maps.json'
STORE=Store(os.getenv('DB_PATH',str(ROOT/'cdl_training.sqlite3')))
intents=discord.Intents.default()
bot=commands.Bot(command_prefix='!',intents=intents,allowed_mentions=discord.AllowedMentions.none())
started=False
OFFICIAL_WATCH=OfficialWatch(ROOT/'official_watch_state.json')
POOL_CANDIDATES=CandidateStore(ROOT/'pool_candidates.json')
KNOWN_MAPS=[x.strip() for x in os.getenv('CDL_CANDIDATE_MAPS','').split(',') if x.strip()]

def maps():
    data=json.loads(MAP_FILE.read_text(encoding='utf8'))
    return {k:sorted(set(v),key=str.lower) for k,v in data.items()}

def is_admin(i):
    return bool(i.guild and i.guild.id==GUILD_ID and i.user.guild_permissions.manage_guild)

def guild_only(i):
    return i.guild is not None and i.guild.id==GUILD_ID

def channel(guild,name):
    return discord.utils.get(guild.channels,name=name)

async def reply(i,message,ephemeral=True):
    if i.response.is_done(): await i.followup.send(message[:1900],ephemeral=ephemeral)
    else: await i.response.send_message(message[:1900],ephemeral=ephemeral)

async def setup_guild(guild):
    created=[]
    for category_name,names in CATEGORIES.items():
        category=discord.utils.get(guild.categories,name=category_name)
        if category is None:
            category=await guild.create_category(category_name,reason='CDL Training Hub setup')
            created.append('category '+category_name)
        for name in names:
            existing=channel(guild,name)
            if existing: continue  # do not alter existing channels
            if name in FORUMS:
                tags=[discord.ForumTag(name=t) for t in FORUM_TAGS[name]]
                await guild.create_forum(name,category=category,available_tags=tags,topic='One post per map / concept. Cite sources and label unverified mechanics.',reason='CDL Training Hub setup')
            else:
                await guild.create_text_channel(name,category=category,reason='CDL Training Hub setup')
            created.append('channel '+name)
    return created

async def get_or_create_thread(guild, mode, map_name, topic):
    forum_name={'hardpoint':'hp-map-library','snd':'snd-map-library','hijack':'hijack-map-library'}[mode]
    forum=channel(guild,forum_name)
    if not isinstance(forum,discord.ForumChannel):
        raise ValueError(f'No forum {forum_name}. Run /setup apply first.')
    thread_name=f'{map_name} | {topic}'[:100]
    # active and archived matching posts; no duplicate thread creation
    for t in forum.threads:
        if t.name.casefold()==thread_name.casefold(): return t
    async for t in forum.archived_threads(limit=100):
        if t.name.casefold()==thread_name.casefold(): return t
    tag=discord.utils.get(forum.available_tags,name=topic.title())
    created=await forum.create_thread(name=thread_name,content=f'**{map_name} — {topic.upper()}**\nUse this thread for verified concepts, source links, practical takeaways and game-version notes.',applied_tags=[tag] if tag else [],reason='CDL Training Hub map topic')
    return created.thread

async def queue_clip(guild_id,url,title,description,mode=None,map_name=None,topic=None,who='system'):
    safe=clean_url(url)
    md=maps()
    inferred=classify(' '.join([title,description]),md)
    mode=mode or inferred[0]
    map_name=map_name or inferred[1]
    topic=topic or inferred[2]
    if mode and mode not in TOPICS: raise ValueError('Invalid mode')
    if mode and map_name and map_name not in md.get(mode,[]): raise ValueError('Map is not configured for that mode')
    if topic and (not mode or topic not in TOPICS[mode]): raise ValueError('Invalid topic for mode')
    conf='manual' if who!='discovery' and mode and map_name and topic else inferred[3]
    return STORE.add(guild_id,safe,title,description,mode,map_name,topic,conf,'reddit' if 'reddit' in safe or 'redd.it' in safe else 'x',who)

async def review_notice(guild,clip_id):
    c=STORE.get(guild.id,clip_id)
    dest=channel(guild,'clips-to-review')
    if isinstance(dest,discord.TextChannel):
        await dest.send(f'**New clip #{clip_id} — review required**\n{discord.utils.escape_markdown(c["title"][:200])}\n{c["url"]}\nProposed: `{c["mode"] or "?"}` / `{c["map_name"] or "?"}` / `{c["topic"] or "?"}`\nUse `/approve clip_id:{clip_id}` (choose mode/map/topic) or `/reject`. ',allowed_mentions=discord.AllowedMentions.none())

@bot.event
async def on_ready():
    global started
    if started: return
    started=True
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f'Logged in as {bot.user}; guild {GUILD_ID}; slash commands synced.')
    if os.getenv('DISCOVERY_ENABLED','false').lower()=='true': discovery_loop.start()
    if os.getenv('OFFICIAL_WATCH_ENABLED','true').lower()=='true': official_watch_loop.start()

@bot.tree.command(name='setup',description='Preview or safely add the study structure',guild=discord.Object(id=GUILD_ID))
@app_commands.describe(action='preview makes no changes; apply creates missing categories/channels')
@app_commands.choices(action=[app_commands.Choice(name='preview',value='preview'),app_commands.Choice(name='apply',value='apply')])
async def setup(i:discord.Interaction,action:app_commands.Choice[str]):
    if not is_admin(i): return await reply(i,'Server Manage Server permission required.')
    if action.value=='preview':
        missing=[name for cat,names in CATEGORIES.items() for name in names if not channel(i.guild,name)]
        missing_cats=[name for name in CATEGORIES if not discord.utils.get(i.guild.categories,name=name)]
        return await reply(i,f'Preview: {len(missing_cats)} categories and {len(missing)} channels missing. No existing channels will be deleted or moved. Use `/setup apply` to create them.')
    await i.response.defer(ephemeral=True,thinking=True)
    try: created=await setup_guild(i.guild)
    except (discord.Forbidden,discord.HTTPException) as err: return await reply(i,f'Setup interrupted; existing changes preserved. Check permissions: {err}')
    await reply(i,f'Setup complete. Created {len(created)} items. Existing channels were left untouched. Configure confirmed maps using `/map-add`.')

@bot.tree.command(name='map-add',description='Add a verified competitive map to a mode',guild=discord.Object(id=GUILD_ID))
@app_commands.choices(mode=[app_commands.Choice(name=n,value=n) for n in TOPICS])
async def map_add(i:discord.Interaction,mode:app_commands.Choice[str],name:str):
    if not is_admin(i): return await reply(i,'Admin permission required.')
    name=' '.join(name.split())[:60]
    if not name or any(x in name for x in ['|','@','`']): return await reply(i,'Invalid map name.')
    data=maps()
    if name.lower() not in [x.lower() for x in data[mode.value]]: data[mode.value].append(name)
    MAP_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    await reply(i,f'Added **{name}** to **{mode.value}**. Forum threads are created on demand when you approve a relevant clip.')

@bot.tree.command(name='submit',description='Submit X/Reddit source to review inbox',guild=discord.Object(id=GUILD_ID))
async def submit(i:discord.Interaction,url:str,title:str,description:str=''):
    if not guild_only(i): return await reply(i,'Use in the configured server.')
    try: clip_id=await queue_clip(i.guild.id,url,title,description,who=str(i.user.id))
    except ValueError as err: return await reply(i,str(err))
    if clip_id is None: return await reply(i,'Already submitted.')
    await review_notice(i.guild,clip_id)
    await reply(i,f'Queued **#{clip_id}** for review. Use `/approve` after checking the clip.')

@bot.tree.command(name='pending',description='Show clips awaiting review',guild=discord.Object(id=GUILD_ID))
async def pending(i:discord.Interaction):
    if not is_admin(i): return await reply(i,'Admin permission required.')
    rows=STORE.pending(i.guild.id)
    await reply(i,'\n'.join(f'#{r["id"]} {r["title"][:75]} ({r["mode"] or "?"}/{r["map_name"] or "?"}/{r["topic"] or "?"})' for r in rows) or 'Queue empty.')

@bot.tree.command(name='approve',description='Verify topic and publish a queued clip',guild=discord.Object(id=GUILD_ID))
@app_commands.choices(mode=[app_commands.Choice(name=n,value=n) for n in TOPICS])
async def approve(i:discord.Interaction,clip_id:int,mode:app_commands.Choice[str],map_name:str,topic:str,lesson:str):
    if not is_admin(i): return await reply(i,'Admin permission required.')
    c=STORE.get(i.guild.id,clip_id)
    if not c or c['status']!='pending': return await reply(i,'Clip does not exist or has already been handled.')
    if map_name not in maps().get(mode.value,[]): return await reply(i,'Unknown map for this mode. Use `/map-add` first.')
    if topic not in TOPICS[mode.value]: return await reply(i,'Invalid topic. Choose one of: '+', '.join(TOPICS[mode.value]))
    if not lesson.strip(): return await reply(i,'A concrete learning takeaway is required.')
    await i.response.defer(ephemeral=True,thinking=True)
    try:
        thread=await get_or_create_thread(i.guild,mode.value,map_name,topic)
        msg=await thread.send(f'**{discord.utils.escape_markdown(c["title"][:150])}**\n**Lesson:** {discord.utils.escape_mentions(lesson[:700])}\n**Source:** {c["url"]}\n**Mode / map / topic:** {mode.value} / {map_name} / {topic}\n**Verification:** approved by {i.user.mention}; mechanics should still be retested after patches.',allowed_mentions=discord.AllowedMentions.none())
        STORE.update(i.guild.id,clip_id,'approved',thread.id,msg.id)
        await reply(i,f'Published clip #{clip_id} in {thread.mention}.')
    except (discord.HTTPException,discord.Forbidden,ValueError) as err:
        await reply(i,f'Publishing failed; item remains pending: {err}')

@bot.tree.command(name='reject',description='Reject a queued source',guild=discord.Object(id=GUILD_ID))
async def reject(i:discord.Interaction,clip_id:int):
    if not is_admin(i): return await reply(i,'Admin permission required.')
    c=STORE.get(i.guild.id,clip_id)
    if not c or c['status']!='pending': return await reply(i,'No such pending clip.')
    STORE.update(i.guild.id,clip_id,'rejected')
    await reply(i,f'Rejected #{clip_id}.')

@bot.tree.command(name='find',description='Search published knowledge items',guild=discord.Object(id=GUILD_ID))
async def find(i:discord.Interaction,query:str):
    if not guild_only(i): return await reply(i,'Use in the configured server.')
    rows=STORE.search(i.guild.id,query)
    await reply(i,'\n'.join(f'#{r["id"]}: {r["title"][:55]} — {r["url"]}' for r in rows) or 'No matching approved items.')

@bot.tree.command(name='content-status',description='Show configured sources and results of the last discovery run',guild=discord.Object(id=GUILD_ID))
async def content_status(i:discord.Interaction):
    if not is_admin(i): return await reply(i,'Admin permission required.')
    cfg=sources.configured()
    state=sources.LAST_RUN
    await reply(i,('**Content collection status**\n'
        f'Reddit API: {"configured" if cfg["reddit"] else "missing credentials"}\n'
        f'X API: {"configured" if cfg["x"] else "missing bearer token"}\n'
        f'Scheduled discovery: {os.getenv("DISCOVERY_ENABLED","false")}\n'
        f'Queries: {len(sources.queries())}\n'
        f'Last run unique links: {state["items"]}\n'
        f'Errors: {"; ".join(state["errors"][:5]) if state["errors"] else "none reported"}\n'
        'No API credentials means no automatic discovery. All discovered clips require approval.'))

@bot.tree.command(name='discover',description='One-off API collection into the moderation queue',guild=discord.Object(id=GUILD_ID))
async def discover_command(i:discord.Interaction):
    if not is_admin(i): return await reply(i,'Admin permission required.')
    await i.response.defer(ephemeral=True,thinking=True)
    n=await run_discovery(i.guild)
    await reply(i,f'Discovery complete: {n} new items queued. API errors: {"; ".join(sources.LAST_RUN["errors"][:3]) or "none"}. Run `/content-status` for details.')

async def run_discovery(guild):
    found=await discover()
    count=0
    for c in found[:80]:
        try: clip_id=await queue_clip(guild.id,c['url'],c['title'],'',who='discovery')
        except ValueError: continue
        if clip_id:
            count+=1
            await review_notice(guild,clip_id)
    return count

@tasks.loop(minutes=max(60,int(os.getenv('DISCOVERY_INTERVAL_MINUTES','60'))))
async def discovery_loop():
    guild=bot.get_guild(GUILD_ID)
    if guild: await run_discovery(guild)

@discovery_loop.before_loop
async def before_discovery(): await bot.wait_until_ready()

async def check_pool_candidates(guild):
    if not KNOWN_MAPS:return 0,['CDL_CANDIDATE_MAPS is empty. Add launch map names to .env for candidate matching.']
    pages,errors=await OFFICIAL_WATCH.fetch_pages()
    found=[]
    for url,html in pages:found.extend(extract_candidates(html,KNOWN_MAPS,url))
    new=POOL_CANDIDATES.add(found)
    dest=channel(guild,'cdl-rules-and-map-pool')
    if isinstance(dest,discord.TextChannel):
        for c in new[:15]:
            await dest.send(f'**POSSIBLE CDL MAP — NOT VERIFIED**\nMode: `{c["mode"]}` | Map: `{c["map"]}`\nEvidence: {discord.utils.escape_mentions(c["evidence"][:300])}\nSource: {c["url"]}\nAdmin must check context and use `/pool-confirm` or `/pool-reject`.',allowed_mentions=discord.AllowedMentions.none())
    return len(new),errors

@bot.tree.command(name='pool-check',description='Find possible map/mode mentions on official sites',guild=discord.Object(id=GUILD_ID))
async def pool_check(i:discord.Interaction):
    if not is_admin(i):return await reply(i,'Admin permission required.')
    await i.response.defer(ephemeral=True,thinking=True)
    n,errors=await check_pool_candidates(i.guild)
    await reply(i,f'New unverified candidates: {n}. Fetch errors: {len(errors)}. '+(' | '.join(errors)[:1200] if errors else 'No fetch errors. No automatic official confirmation.'))

@bot.tree.command(name='pool-pending',description='Review possible official map/mode matches',guild=discord.Object(id=GUILD_ID))
async def pool_pending(i:discord.Interaction):
    if not is_admin(i):return await reply(i,'Admin permission required.')
    rows=POOL_CANDIDATES.pending()
    await reply(i,'\n'.join(f'{c["mode"]} / {c["map"]}: {c["url"]}' for c in rows[:15]) or 'No unverified map candidates.')

@bot.tree.command(name='pool-confirm',description='Confirm a map/mode after checking an official announcement',guild=discord.Object(id=GUILD_ID))
@app_commands.choices(mode=[app_commands.Choice(name=n,value=n) for n in TOPICS])
async def pool_confirm(i:discord.Interaction,mode:app_commands.Choice[str],map_name:str,official_url:str):
    if not is_admin(i):return await reply(i,'Admin permission required.')
    if not is_official(official_url):return await reply(i,'Use a verified official CDL/Call of Duty HTTPS source.')
    if not map_name.strip() or any(c in map_name for c in '|@`') or len(map_name)>60:return await reply(i,'Invalid map name.')
    await i.response.defer(ephemeral=True,thinking=True)
    data=maps();name=map_name.strip()
    if name.casefold() not in {x.casefold() for x in data[mode.value]}:data[mode.value].append(name)
    MAP_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    POOL_CANDIDATES.set_status(mode.value,name,'confirmed')
    threads=[]
    for topic in TOPICS[mode.value]:
        try:
            thread=await get_or_create_thread(i.guild,mode.value,name,topic)
            threads.append(thread)
        except (discord.HTTPException,discord.Forbidden,ValueError) as e:
            await reply(i,f'Map saved, but forum creation stopped after {len(threads)} threads: {e}')
            return
    dest=channel(i.guild,'cdl-rules-and-map-pool')
    if isinstance(dest,discord.TextChannel):
        await dest.send(f'**Admin-confirmed CDL map**: {name} / {mode.value}\nSource: {official_url}\n{len(threads)} study threads prepared.',allowed_mentions=discord.AllowedMentions.none())
    await reply(i,f'Confirmed {name} / {mode.value}; created or reused {len(threads)} forum threads.')

@bot.tree.command(name='pool-reject',description='Reject unverified map candidate',guild=discord.Object(id=GUILD_ID))
@app_commands.choices(mode=[app_commands.Choice(name=n,value=n) for n in TOPICS])
async def pool_reject(i:discord.Interaction,mode:app_commands.Choice[str],map_name:str):
    if not is_admin(i):return await reply(i,'Admin permission required.')
    n=POOL_CANDIDATES.set_status(mode.value,map_name,'rejected')
    await reply(i,f'Rejected {n} candidate entries. Existing confirmed maps unchanged.')

@bot.tree.command(name='official-check',description='Check official CDL/patch pages for changes',guild=discord.Object(id=GUILD_ID))
async def official_check(i:discord.Interaction):
    if not is_admin(i): return await reply(i,'Admin permission required.')
    await i.response.defer(ephemeral=True,thinking=True)
    changes=await OFFICIAL_WATCH.check()
    await send_official_changes(i.guild,changes)
    await reply(i,('Changed official pages: '+', '.join(changes)) if changes else 'No changes detected (or first baseline saved). This does NOT confirm a CDL map pool.')

async def send_official_changes(guild,changes):
    if not changes: return
    dest=channel(guild,'cdl-rules-and-map-pool')
    if not isinstance(dest,discord.TextChannel): return
    for url in changes:
        await dest.send('**Official source updated — REVIEW REQUIRED**\n'+url+'\nA page change does not establish which maps are official. Verify the announcement and mode/map assignments before updating `maps.json`.',allowed_mentions=discord.AllowedMentions.none())

@tasks.loop(hours=6)
async def official_watch_loop():
    guild=bot.get_guild(GUILD_ID)
    if guild:
        changes=await OFFICIAL_WATCH.check()
        await send_official_changes(guild,changes)
        await check_pool_candidates(guild)

@official_watch_loop.before_loop
async def before_official_watch(): await bot.wait_until_ready()

@bot.tree.error
async def on_app_command_error(i,error):
    print('Command error:',repr(error))
    await reply(i,'Command failed. Check the bot logs and permissions.')

if __name__=='__main__': bot.run(TOKEN,log_handler=None)
