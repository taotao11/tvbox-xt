from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl
from .db import get_video, init_db, list_videos, upsert_video
from .sniffer import VideoSniffer

sniffer=VideoSniffer()

class BrowseRequest(BaseModel):
    url: HttpUrl

@asynccontextmanager
async def lifespan(app):
    init_db()
    await sniffer.start()
    async def consume():
        while True:
            e=await sniffer.next_event()
            upsert_video(e["title"],e["category"],e["page_url"],e)
    task=asyncio.create_task(consume())
    yield
    task.cancel()
    await sniffer.stop()

app=FastAPI(title="TVBox Video Sniffer",version="1.0.0",lifespan=lifespan)

@app.get("/",response_class=HTMLResponse)
def index():
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>TVBox 视频嗅探器</title>
<style>body{font-family:Arial;background:#111;color:#eee;margin:0}header{padding:20px;background:#181818;position:sticky;top:0}input{padding:10px;width:65%;background:#222;color:#fff;border:1px solid #444}button{padding:10px 16px}.card{background:#1c1c1c;margin:10px 20px;padding:16px;border-radius:8px}small{color:#aaa}.tag{padding:3px 8px;border:1px solid #555;border-radius:10px;margin-left:8px}a{color:#7dd3fc}</style></head>
<body><header><b>🎬 TVBox 视频嗅探器</b><br><br>
<input id="url" placeholder="输入有权访问的视频网站 URL"><button onclick="browse()">打开并嗅探</button>
<a href="/api/tvbox" target="_blank" style="margin-left:15px">TVBox API</a></header><main id="list">加载中...</main>
<script>
async function browse(){const url=document.getElementById('url').value.trim();if(!url)return;const r=await fetch('/api/browse',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url})});alert((await r.json()).message)}
async function load(){const r=await fetch('/api/videos?limit=200');const d=await r.json();document.getElementById('list').innerHTML=d.map(v=>'<div class="card"><b>'+esc(v.title)+'</b><span class="tag">'+esc(v.category)+'</span><br><small>'+esc(v.domain||'')+' · '+esc(v.page_url)+'</small><br><a href="/api/vod/detail?id='+v.id+'" target="_blank">查看详情</a></div>').join('')}
function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
load();setInterval(load,3000);
</script></main></body></html>"""

@app.post("/api/browse")
async def browse(req:BrowseRequest):
    await sniffer.browse(str(req.url))
    return {"ok":True,"message":"浏览器已打开，播放视频后会自动捕获媒体请求"}

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
    for r in rows: classes.setdefault(r["category"],len(classes)+1)
    return {"class":[{"type_id":i,"type_name":n} for n,i in classes.items()],
            "list":[{"vod_id":str(r["id"]),"vod_name":r["title"],"vod_pic":r.get("cover") or "","vod_remarks":r["category"]} for r in rows]}

if __name__=="__main__":
    import uvicorn
    uvicorn.run("app.main:app",host="0.0.0.0",port=9978,reload=False)
