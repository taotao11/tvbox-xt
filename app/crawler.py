from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

from playwright.async_api import Page

from .db import record_crawl_page

class SiteCrawler:
    """Same-domain crawler for sites the operator is authorized to crawl."""

    def __init__(self, sniffer):
        self.sniffer = sniffer
        self.running = False
        self.stats = {"queued": 0, "visited": 0, "videos": 0, "errors": 0}

    @staticmethod
    def normalize(url: str) -> str:
        url, _ = urldefrag(url)
        return url.rstrip("/") or url

    @staticmethod
    def same_site(url: str, root: str) -> bool:
        a, b = urlparse(url), urlparse(root)
        return a.scheme in ("http", "https") and a.netloc == b.netloc

    async def extract_links(self, page: Page, root: str) -> list[str]:
        links = await page.locator("a[href]").evaluate_all("els => els.map(a => a.href).filter(Boolean)")
        out = []
        for link in links:
            link = self.normalize(urljoin(page.url, link))
            if self.same_site(link, root):
                out.append(link)
        return list(dict.fromkeys(out))

    async def trigger_video_players(self, page: Page):
        try:
            await page.locator("video").evaluate_all("""els => els.forEach(v => {
                try { const p=v.play(); if (p && p.catch) p.catch(()=>{}); } catch(e) {}
            })""")
        except Exception:
            pass
        try:
            await page.locator("button[aria-label*='play' i],button[title*='play' i],[role='button'][aria-label*='play' i]").evaluate_all(
                """els => els.slice(0,5).forEach(e => { try { e.click(); } catch(x) {} })"""
            )
        except Exception:
            pass

    async def crawl(self, start_url: str, max_pages: int = 1000, max_depth: int = 20, delay_ms: int = 250):
        start_url = self.normalize(start_url)
        root = start_url
        queue = deque([(start_url, 0)])
        seen = set()
        self.running = True
        self.stats = {"queued": 1, "visited": 0, "videos": 0, "errors": 0}
        try:
            while queue and len(seen) < max_pages and self.running:
                url, depth = queue.popleft()
                if url in seen or depth > max_depth:
                    continue
                seen.add(url)
                self.stats["visited"] = len(seen)
                try:
                    await self.sniffer.browse(url)
                    title = await self.sniffer.page.title()
                    await self.trigger_video_players(self.sniffer.page)
                    await asyncio.sleep(max(delay_ms, 0) / 1000)
                    links = await self.extract_links(self.sniffer.page, root)
                    record_crawl_page(url, title=title, depth=depth, status="visited", media_count=0)
                    for link in links:
                        if link not in seen and len(seen) + len(queue) < max_pages:
                            queue.append((link, depth + 1))
                    self.stats["queued"] = len(queue)
                except Exception as exc:
                    record_crawl_page(url, depth=depth, status="error", error=str(exc)[:1000])
                    self.stats["errors"] += 1
                await asyncio.sleep(max(delay_ms, 0) / 1000)
        finally:
            self.running = False
        return dict(self.stats)

    def stop(self):
        self.running = False
