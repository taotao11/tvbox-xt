from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl

from .crawler import SiteCrawler
from .db import get_video, init_db, list_videos, upsert_video
from .sniffer import VideoSniffer

sniffer=VideoSniffer()
crawler=SiteCrawler(sniffer)
crawl_task=None
runtime={"events":0,"last_error":""}

class BrowseRequest(BaseModel):
    url: HttpUrl

class CrawlRequest(BaseModel):
    url: HttpUrl
    max_pages: int = 1000
    max_depth: int = 20
    delay_ms: int = 250

@asynccontextmanager
async def lifespan(app):
    global crawl_task
    init_db()
    await sniffer.start()

    async def consume():
        while True:
            e=await sniffer.next_event()
            try:
                upsert_video(e["title"],e["category"],e["page_url"],e)
                runtime["events"] += 1
            except Exception as exc:
                runtime["last_error"]=str(exc)

    consumer=asyncio.create_task(consume())

    # Optional automatic crawl:
    # set SITE_URL=https://example.com before starting the server.
    site_url=os.getenv("SITE_URL","").strip()
    if site_url:
        crawl_task=asyncio.create_task(crawler.crawl(site_url))

    yield

    crawler.stop()
    if crawl_task:
        crawl_task.cancel()
    consumer.cancel()
    await sniffer.stop()

app=FastAPI(title="TVBox XT Site Video Crawler",version="2.0.0",lifespan=lifespan)

@app.get("/",response_class=HTMLResponse)
def index():
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TVBox XT · 全站视频采集</title>
<style>
body{font-family:system-ui,Arial;background:#0b0f14;color:#eee;margin:0}
header{padding:22px;background:#121923;position:sticky;top:0;z-index:2;border-bottom:1px solid #263241}
input{padding:10px;width:42%;min-width:260px;background:#0d131b;color:#fff;border:1px solid #344255;border-radius:6px}
button{padding:10px 15px;margin-left:6px;border:0;border-radius:6px;cursor:pointer}
.card{background:#151d27;margin:10px 20px;padding:16px;border-radius:8px;border:1px solid #263241}
small{color:#9aa8b8}.tag{padding:3px 8px;border:1px solid #536174;border-radius:10px;margin-left:8px}
a{color:#7dd3fc}.stats{margin-top:12px;color:#aab7c7}
</style></head>
<body><header>
<b>🎬 TVBox XT · 特定网站全站视频采集器</b><div style="margin-top:14px">
<input id="url" placeholder="输入你有权访问的网站首页，例如 https://example.com">
<input id="max" type="number" value="1000" min="1" max="10000" style="width:100px"><button onclick="crawl()">开始全站采集</button>
<button onclick="stop()">停止</button><a href="/api/tvbox" target="_blank" style="margin-left:15px">TVBox API</a>
</div><div id="stats" class="stats">状态：空闲</div></header>
<main id="list">加载中...</main>
<script>
async function crawl(){
 const url=document.getElementById('url').value.trim(); if(!url)return;
 const max=Number(document.getElementById('max').value)||1000;
 const r=await fetch('/api/crawl',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url,max_pages:max})});
 const d=await r.json(); alert(d.message||JSON.stringify(d));
}
async function stop(){await fetch('/api/crawl/stop',{method:'POST'});}
async function status(){const r=await fetch('/api/crawl/status');const d=await r.json();
 document.getElementById('stats').textContent='状态：'+(d.running?'采集中':'空闲')+' · 已访问 '+d.visited+' 页 · 队列 '+d.queued+' · 捕获媒体请求 '+d.events+' · 错误 '+d.errors;
}
async function load(){const r=await fetch('/api/videos?limit=200');const d=await r.json();
 document.getElementById('list').innerHTML=d.map(v=>'<div class="card"><b>'+esc(v.title)+'</b><span class="tag">'+esc(v.category)+'</span><br><small>'+esc(v.domain||'')+' · '+esc(v.page_url)+'</small><br><a href="/api/vod/detail?id='+v.id+'" target="_blank">查看详情</a></div>').join('');
}
function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
load(); status(); setInterval(load,3000); setInterval(status,1000);
</script></main></body></html>"""

@app.post("/api/browse")
async def browse(req:BrowseRequest):
    await sniffer.browse(str(req.url))
    return {"ok":True,"message":"已打开页面。播放视频或让页面自动加载媒体后，媒体请求会保存到SQLite。"}

@app.post("/api/crawl")
async def start_crawl(req:CrawlRequest):
    global crawl_task
    if crawler.running:
        return {"ok":False,"message":"已有采集任务正在运行","status":crawler.stats}
    crawler.stop()
    crawl_task=asyncio.create_task(
        crawler.crawl(str(req.url),max_pages=req.max_pages,max_depth=req.max_depth,delay_ms=req.delay_ms)
    )
    return {"ok":True,"message":"已开始从该站点首页递归发现同域页面并采集视频","status":crawler.stats}

@app.post("/api/crawl/stop")
async def stop_crawl():
    crawler.stop()
    return {"ok":True,"message":"已请求停止采集","status":crawler.stats}

@app.get("/api/crawl/status")
def crawl_status():
    return {"running":crawler.running,**crawler.stats,**runtime}

@app.get("/api/videos")
def videos(category:str|None=None,q:str|None=None,limit:int=Query(100,le=500)):
    return list_videos(category,q,limit)

@app.get("/api/vod/detail")
def detail(id:int):
    item=get_video(id)
    if not item: raise HTTPException(404,"video not found")
    return item

@app.get("/api/vod/play")
def play(id:int,episode:int=0):
    item=get_video(id)
    if not item or not item["streams"]: raise HTTPException(404,"stream not found")
    s=item["streams"][min(episode,len(item["streams"])-1)]
    return {"url":s["url"],"parse":0,"header":s["headers_json"]}

@app.get("/api/tvbox")
def tvbox():
    rows=list_videos(limit=500)
    classes={}
    for r in rows:
        classes.setdefault(r["category"],len(classes)+1)
    return {
        "class":[{"type_id":i,"type_name":n} for n,i in classes.items()],
        "list":[{"vod_id":str(r["id"]),"vod_name":r["title"],"vod_pic":r.get("cover") or "","vod_remarks":r["category"]} for r in rows]
    }

if __name__=="__main__":
    import uvicorn
    uvicorn.run("app.main:app",host="0.0.0.0",port=9978,reload=False)
