"""Monitor configured official announcement pages; never infer map pool from unstructured text."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import aiohttp

DEFAULT_URLS = [
    'https://www.callofdutyleague.com/',
    'https://www.callofduty.com/patchnotes',
]
ALLOWED = {'callofdutyleague.com', 'www.callofdutyleague.com', 'callofduty.com', 'www.callofduty.com'}

class OfficialWatch:
    def __init__(self, path):
        self.path=Path(path)
        try: self.state=json.loads(self.path.read_text())
        except (OSError,ValueError): self.state={}

    async def check(self, urls=None):
        urls=urls or DEFAULT_URLS
        changes=[]
        async with aiohttp.ClientSession(headers={'User-Agent':'CDLTrainingHub/1.1 (+official change alerts)'}) as session:
            for url in urls:
                parsed=urlsplit(url)
                if parsed.scheme!='https' or parsed.hostname not in ALLOWED: continue
                try:
                    async with session.get(url,timeout=aiohttp.ClientTimeout(total=20),allow_redirects=True) as response:
                        response.raise_for_status()
                        if response.url.host not in ALLOWED: continue
                        body=await response.read()
                        if len(body)>4_000_000: continue
                        digest=hashlib.sha256(body).hexdigest()
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    print('Official watch request failed:',url,str(e)); continue
                previous=self.state.get(url)
                if previous and previous!=digest: changes.append(url)
                self.state[url]=digest
        self.path.write_text(json.dumps(self.state,indent=2))
        return changes

    async def fetch_pages(self, urls=None):
        """Fetch official HTML for candidate extraction; failures are reported."""
        urls=urls or DEFAULT_URLS
        pages=[]; errors=[]
        async with aiohttp.ClientSession(headers={'User-Agent':'CDLTrainingHub/2.0'}) as session:
            for url in urls:
                p=urlsplit(url)
                if p.scheme!='https' or p.hostname not in ALLOWED:continue
                try:
                    async with session.get(url,timeout=aiohttp.ClientTimeout(total=20)) as r:
                        r.raise_for_status()
                        if r.url.host not in ALLOWED:raise ValueError('Redirected to non-official host')
                        if 'html' not in r.headers.get('Content-Type',''):continue
                        raw=await r.content.read(2_000_001)
                        if len(raw)>2_000_000:raise ValueError('Page too large')
                        pages.append((url,raw.decode('utf-8',errors='replace')))
                except (aiohttp.ClientError,asyncio.TimeoutError,ValueError) as e:
                    errors.append(f'{url}: {type(e).__name__}: {e}')
        return pages,errors
