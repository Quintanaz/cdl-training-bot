"""Monitor configured official announcement pages; never infer map pool from unstructured text."""
import asyncio
import hashlib
import json
import os
import re
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlsplit
import aiohttp
from playwright.async_api import async_playwright

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

    def _digest(self, body):
        soup = BeautifulSoup(body, "html.parser")

        for element in soup(["script", "style", "noscript", "svg", "iframe"]):
            element.decompose()

        for element in soup.select(
            "header, footer, nav, aside, form, "
            "[role=navigation], [role=banner], "
            "[aria-live], [data-testid*=cookie]"
        ):
            element.decompose()

        main = soup.select_one("main, article, [role=main]")
        content = main if main else soup.body or soup

        text = content.get_text(" ", strip=True)
        text = re.sub(r"\\s+", " ", text).strip()

        if len(text) < 100:
            return None

        return hashlib.sha256(text.encode("utf-8")).hexdigest()


    async def _render_cdl(self):
        """Render CDL with JavaScript and extract announcement headlines."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                await page.goto(
                    "https://www.callofdutyleague.com/",
                    wait_until="domcontentloaded",
                    timeout=45000,
                )

                await page.wait_for_timeout(5000)

                if urlsplit(page.url).hostname not in ALLOWED:
                    return None

                headings = await page.locator(
                    "h1, h2, h3, h4"
                ).all_inner_texts()

                headings = [
                    " ".join(text.split())
                    for text in headings
                    if len(text.strip()) >= 10
                ]

                if not headings:
                    return None

                content = "\\n".join(sorted(set(headings)))
                return hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest()

            finally:
                await browser.close()

    async def check(self, urls=None):
        if not hasattr(self, "_lock"):
            self._lock = asyncio.Lock()

        async with self._lock:
            urls = urls or DEFAULT_URLS
            changes = []

            async with aiohttp.ClientSession(
                headers={"User-Agent": "CDLTrainingHub/2.1"}
            ) as session:
                for url in urls:
                    parsed = urlsplit(url)
                    if parsed.scheme != "https" or parsed.hostname not in ALLOWED:
                        continue

                    try:
                        async with session.get(
                            url,
                            timeout=aiohttp.ClientTimeout(total=20),
                            allow_redirects=True,
                        ) as response:
                            response.raise_for_status()

                            if response.url.host not in ALLOWED:
                                continue

                            if "html" not in response.headers.get("Content-Type", ""):
                                continue

                            body = await response.content.read(4_000_001)
                            if len(body) > 4_000_000:
                                continue

                            if parsed.hostname in {
                                "callofdutyleague.com",
                                "www.callofdutyleague.com",
                            }:
                                digest = await self._render_cdl()
                            else:
                                digest = self._digest(body)

                            if digest is None:
                                continue

                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        print("Official watch request failed:", url, str(e))
                        continue

                    previous = self.state.get(url)

                    if not isinstance(previous, dict):
                        self.state[url] = {
                            "confirmed": digest,
                            "pending": None,
                            "count": 0,
                        }
                        continue

                    confirmed = previous.get("confirmed")

                    if digest == confirmed:
                        previous["pending"] = None
                        previous["count"] = 0
                        continue

                    if digest == previous.get("pending"):
                        previous["count"] = previous.get("count", 0) + 1
                    else:
                        previous["pending"] = digest
                        previous["count"] = 1

                    if previous["count"] >= 2:
                        changes.append(url)
                        previous["confirmed"] = digest
                        previous["pending"] = None
                        previous["count"] = 0

            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self.state, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.path)

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
