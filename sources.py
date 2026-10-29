"""Official API-based Reddit/X discovery. Never scrape, download, or repost video."""
import asyncio
import os
import re
import aiohttp

DEFAULT_QUERIES = [
    '"MW4" "hardpoint" spawn', '"MW4" "hardpoint" rotation',
    '"MW4" "snd" nade', '"MW4" "search and destroy" strat',
    '"MW4" "hijack" spike', '"CDL" "hardpoint" setup',
]
LAST_RUN = {'items': 0, 'errors': [], 'sources': {}, 'queries': []}


def queries():
    raw=os.getenv('CONTENT_SEARCH_QUERIES','').strip()
    return [s.strip() for s in raw.split(';') if s.strip()][:20] if raw else DEFAULT_QUERIES


def configured():
    return {
        'reddit': bool(all(os.getenv(k) for k in ('REDDIT_CLIENT_ID','REDDIT_CLIENT_SECRET','REDDIT_USER_AGENT'))),
        'x': bool(os.getenv('X_BEARER_TOKEN')),
    }

async def reddit_token(session):
    auth=aiohttp.BasicAuth(os.environ['REDDIT_CLIENT_ID'],os.environ['REDDIT_CLIENT_SECRET'])
    headers={'User-Agent':os.environ['REDDIT_USER_AGENT']}
    async with session.post('https://www.reddit.com/api/v1/access_token',auth=auth,data={'grant_type':'client_credentials'},headers=headers,timeout=aiohttp.ClientTimeout(total=20)) as r:
        r.raise_for_status()
        return (await r.json())['access_token']

async def reddit_search(session,query,token):
    headers={'Authorization':'bearer '+token,'User-Agent':os.environ['REDDIT_USER_AGENT']}
    async with session.get('https://oauth.reddit.com/r/CoDCompetitive/search',params={'q':query,'restrict_sr':'on','sort':'new','t':'week','limit':25},headers=headers,timeout=aiohttp.ClientTimeout(total=20)) as r:
        r.raise_for_status()
        data=await r.json()
    return [{'url':'https://www.reddit.com'+p['data']['permalink'],'title':p['data'].get('title',''),'source':'reddit'} for p in data.get('data',{}).get('children',[]) if not p['data'].get('over_18') and p['data'].get('permalink')]

async def x_search(session,query):
    # X recent-search access is plan-dependent. 429/403 errors are reported, never bypassed.
    handles=[s.strip().lstrip('@') for s in os.getenv('X_ACCOUNTS','').split(',') if re.fullmatch(r'@?[A-Za-z0-9_]{1,15}',s.strip())]
    if handles:
        query='('+query+') ('+' OR '.join('from:'+h for h in handles[:10])+')'
    async with session.get('https://api.x.com/2/tweets/search/recent',params={'query':query+' -is:retweet lang:en','max_results':20,'tweet.fields':'created_at,author_id'},headers={'Authorization':'Bearer '+os.environ['X_BEARER_TOKEN']},timeout=aiohttp.ClientTimeout(total=20)) as r:
        r.raise_for_status()
        data=await r.json()
    return [{'url':f'https://x.com/i/web/status/{p["id"]}','title':p.get('text','')[:290],'source':'x'} for p in data.get('data',[])]

async def discover():
    global LAST_RUN
    conf=configured()
    state={'items':0,'errors':[],'sources':{'reddit':0,'x':0},'queries':queries()}
    found=[]
    async with aiohttp.ClientSession() as session:
        token=None
        if conf['reddit']:
            try: token=await reddit_token(session)
            except (aiohttp.ClientError,TimeoutError,KeyError,ValueError) as exc:
                state['errors'].append('reddit auth: '+str(exc)[:160])
        for query in state['queries']:
            if token:
                try:
                    items=await reddit_search(session,query,token)
                    found.extend(items);state['sources']['reddit']+=len(items)
                except (aiohttp.ClientError,TimeoutError,KeyError,ValueError) as exc:
                    state['errors'].append('reddit search: '+str(exc)[:160])
            if conf['x']:
                try:
                    items=await x_search(session,query)
                    found.extend(items);state['sources']['x']+=len(items)
                except (aiohttp.ClientError,TimeoutError,KeyError,ValueError) as exc:
                    state['errors'].append('x search: '+str(exc)[:160])
    seen=set()
    unique=[p for p in found if not (p['url'] in seen or seen.add(p['url']))]
    state['items']=len(unique)
    LAST_RUN=state
    return unique
