from __future__ import annotations
import asyncio, re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

MEDIA_EXTENSIONS=(".m3u8",".mp4",".m4v",".webm",".flv",".mov",".ts",".mpd")
MEDIA_TYPES=("video/","application/vnd.apple.mpegurl","application/x-mpegurl","application/dash+xml")

def looks_like_media(url, content_type=""):
    path=urlparse(url).path.lower()
    return any(path.endswith(x) for x in MEDIA_EXTENSIONS) or any(content_type.lower().startswith(x) for x in MEDIA_TYPES)

def classify(title,url):
    text=(title+" "+url).lower()
    rules=[
        (("动漫","anime","cartoon"),"动漫"),
        (("综艺","variety","show"),"综艺"),
        (("纪录","documentary"),"纪录片"),
        (("短视频","short","reel"),"短视频"),
        (("电影","movie","film"),"电影"),
        (("电视剧","剧集","series","episode","tv"),"电视剧"),
    ]
    for keys,name in rules:
        if any(k in text for k in keys): return name
    return "其他"

def clean_title(title):
    title=re.sub(r"\s+"," ",title or "").strip()
    return title[:300] or "未命名视频"

class VideoSniffer:
    def __init__(self):
        self.pw=None
        self.browser=None
        self.page=None
        self.events=asyncio.Queue()

    async def start(self):
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(headless=False)
        self.page=await self.browser.new_page()
        self.page.on("response", self._on_response)
        await self.page.goto("about:blank")

    async def _on_response(self, response):
        try:
            ctype=response.headers.get("content-type","")
            if not looks_like_media(response.url,ctype):
                return
            headers=dict(response.request.headers)
            title=clean_title(await self.page.title())
            event={
                "title":title,
                "category":classify(title,self.page.url),
                "page_url":self.page.url,
                "url":response.url,
                "stream_type":"m3u8" if ".m3u8" in response.url.lower() else ("mpd" if ".mpd" in response.url.lower() else "media"),
                "referer":headers.get("referer",""),
                "user_agent":headers.get("user-agent",""),
                "headers":{k:v for k,v in headers.items() if k.lower() in {"referer","origin","user-agent","cookie"}}
            }
            await self.events.put(event)
        except Exception:
            pass

    async def browse(self,url):
        if not self.page:
            raise RuntimeError("sniffer not started")
        await self.page.goto(url,wait_until="domcontentloaded",timeout=30000)

    async def next_event(self):
        return await self.events.get()

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
