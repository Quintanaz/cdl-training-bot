"""Monitor official CDL competitive settings with confirmed changes."""

import asyncio
import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright


URL = "https://callofdutyleague.com/en-us/competitive-settings"

START = "PRO/CHALLENGERS SETTINGS"
END = "STAY CONNECTED"


class CompetitiveSettingsWatch:

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

        self.state_file = self.directory / "state.json"
        self.history_dir = self.directory / "history"
        self.history_dir.mkdir(exist_ok=True)

        try:
            self.state = json.loads(
                self.state_file.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            self.state = {}

        self.lock = asyncio.Lock()

    async def fetch(self):
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)

            try:
                page = await browser.new_page()

                response = await page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=45000,
                )

                if not response or response.status != 200:
                    raise RuntimeError("Competitive Settings unavailable")

                await page.wait_for_timeout(5000)

                parsed = urlsplit(page.url)

                if (
                    parsed.scheme != "https"
                    or parsed.hostname not in {
                        "callofdutyleague.com",
                        "www.callofdutyleague.com",
                    }
                    or parsed.path.rstrip("/") !=
                    "/en-us/competitive-settings"
                ):
                    raise RuntimeError("Unexpected redirect")

                # Read rendered content before filtering.
                # Removing header elements can accidentally remove
                # competitive settings on this JavaScript-driven site.
                text = await page.locator("body").inner_text()

                return self.normalize(text)

            finally:
                await browser.close()

    @staticmethod
    def normalize(text):
        text = text.replace("\r", "")

        if START not in text:
            raise RuntimeError("Competitive settings section missing")

        text = text[text.index(START):]

        if END in text:
            text = text[:text.index(END)]

        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
        ]

        lines = [line for line in lines if line]

        result = "\n".join(lines)

        required = [
            "MAPS & MODES LIST",
            "SEARCH & DESTROY",
            "HARDPOINT",
            "RESTRICTED ITEMS",
        ]

        missing = [item for item in required if item not in result]

        if missing:
            raise RuntimeError(
                "Missing expected sections: " + ", ".join(missing)
            )

        if len(result) < 500:
            raise RuntimeError("Competitive settings content too short")

        return result

    def save_state(self):
        temporary = self.state_file.with_suffix(".tmp")

        temporary.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        temporary.replace(self.state_file)

    def save_version(self, content, digest):
        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%d_%H%M%S"
        )

        path = self.history_dir / f"{timestamp}_{digest[:12]}.txt"

        path.write_text(content, encoding="utf-8")

    async def check(self):
        async with self.lock:
            content = await self.fetch()

            digest = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()

            confirmed = self.state.get("confirmed")
            previous_content = self.state.get("content", "")

            # First run: establish baseline without alert.
            if not confirmed:
                self.state = {
                    "confirmed": digest,
                    "content": content,
                    "pending": None,
                    "count": 0,
                }

                self.save_version(content, digest)
                self.save_state()

                return {
                    "status": "baseline",
                    "changes": [],
                }

            if digest == confirmed:
                self.state["pending"] = None
                self.state["count"] = 0
                self.save_state()

                return {
                    "status": "unchanged",
                    "changes": [],
                }

            if self.state.get("pending") == digest:
                self.state["count"] = (
                    self.state.get("count", 0) + 1
                )
            else:
                self.state["pending"] = digest
                self.state["count"] = 1

            if self.state["count"] < 2:
                self.save_state()

                return {
                    "status": "pending",
                    "changes": [],
                }

            diff = list(
                difflib.unified_diff(
                    previous_content.splitlines(),
                    content.splitlines(),
                    fromfile="Previous CDL settings",
                    tofile="Updated CDL settings",
                    lineterm="",
                )
            )

            self.state = {
                "confirmed": digest,
                "content": content,
                "pending": None,
                "count": 0,
            }

            self.save_version(content, digest)
            self.save_state()

            return {
                "status": "changed",
                "changes": diff,
            }


if __name__ == "__main__":

    async def main():
        watcher = CompetitiveSettingsWatch(
            Path(__file__).resolve().parent
            / "competitive_settings_state"
        )

        result = await watcher.check()

        print("STATUS:", result["status"])

        if result["changes"]:
            print("\n".join(result["changes"][:100]))

    asyncio.run(main())
