from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl

from .crawler import SiteCrawler
from .db import get_video, init_db, list_videos, upsert_video, list_crawl_pages, list_streams, crawl_summary
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
    site_url=os.getenv("SITE_URL","").strip()
    if site_url:
        crawl_task=asyncio.create_task(crawler.crawl(site_url))
    yield
    crawler.stop()
    if crawl_task:
        crawl_task.cancel()
    consumer.cancel()
    await sniffer.stop()

app=FastAPI(title="TVBox XT Site Video Crawler",version="2.1.0",lifespan=lifespan)

@app.get("/",response_class=HTMLResponse)
def index():
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TVBox XT · 采集管理中心</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,Arial;background:#0b0f14;color:#e8eef5;margin:0}
header{padding:22px;background:#121923;position:sticky;top:0;z-index:2;border-bottom:1px solid #263241}
input{padding:10px;width:42%;min-width:260px;background:#0d131b;color:#fff;border:1px solid #344255;border-radius:6px}
button,.tab{padding:10px 15px;margin-left:6px;border:0;border-radius:6px;cursor:pointer;background:#243244;color:#fff}
button.primary,.tab.active{background:#2563eb}.card{background:#151d27;margin:10px 20px;padding:16px;border-radius:8px;border:1px solid #263241}
small{color:#9aa8b8}.tag{padding:3px 8px;border:1px solid #536174;border-radius:10px;margin-left:8px}
a{color:#7dd3fc}.stats{margin-top:12px;color:#aab7c7}.tabs{padding:14px 20px 0}.panel{display:none}.panel.active{display:block}
table{width:calc(100% - 40px);margin:10px 20px;border-collapse:collapse;background:#111923}
th,td{padding:10px;border-bottom:1px solid #263241;text-align:left;vertical-align:top;font-size:13px}th{color:#9fb0c3;position:sticky;top:0;background:#17212d}
.url{max-width:650px;word-break:break-all}.empty{padding:30px 20px;color:#8fa0b3}
.kpis{display:flex;gap:10px;padding:10px 20px}.kpi{background:#151d27;border:1px solid #263241;border-radius:8px;padding:12px 18px}.kpi b{font-size:22px;display:block}
</style></head>
<body><header>
<b>🎬 TVBox XT · 全站采集管理中心</b><div style="margin-top:14px">
<input id="url" placeholder="输入你有权访问的网站首页，例如 https://example.com">
<input id="max" type="number" value="1000" min="1" max="10000" style="width:100px"><button class="primary" onclick="crawl()">开始全站采集</button>
<button onclick="stop()">停止</button><a href="/api/tvbox" target="_blank" style="margin-left:15px">TVBox API</a>
</div><div id="stats" class="stats">状态：空闲</div></header>
<div class="kpis"><div class="kpi">已爬页面<b id="kp">0</b></div><div class="kpi">视频<b id="kv">0</b></div><div class="kpi">媒体流<b id="ks">0</b></div></div>
<div class="tabs"><button class="tab active" onclick="tab('videos',this)">视频资源</button><button class="tab" onclick="tab('streams',this)">媒体流</button><button class="tab" onclick="tab('pages',this)">已爬页面</button></div>
<section id="videos" class="panel active"><div id="videoList">加载中...</div></section>
<section id="streams" class="panel"><table><thead><tr><th>视频</th><th>类型</th><th>媒体 URL</th><th>来源页面</th><th>最后发现</th></tr></thead><tbody id="streamList"></tbody></table></section>
<section id="pages" class="panel"><table><thead><tr><th>标题</th><th>深度</th><th>状态</th><th>页面 URL</th><th>最后访问</th><th>错误</th></tr></thead><tbody id="pageList"></tbody></table></section>
<script>
let current='videos';
function tab(name,el){current=name;document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));document.getElementById(name).classList.add('active');document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));el.classList.add('active');load()}
async function crawl(){const url=document.getElementById('url').value.trim();if(!url)return alert('请输入网站首页');const max=Number(document.getElementById('max').value)||1000;const r=await fetch('/api/crawl',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({url,max_pages:max})});const d=await r.json();alert(d.message||JSON.stringify(d))}
async function stop(){await fetch('/api/crawl/stop',{method:'POST'})}
async function status(){const r=await fetch('/api/crawl/status');const d=await r.json();document.getElementById('stats').textContent='状态：'+(d.running?'采集中':'空闲')+' · 已访问 '+d.visited+' 页 · 队列 '+d.queued+' · 捕获媒体请求 '+d.events+' · 错误 '+d.errors;document.getElementById('kp').textContent=d.pages;document.getElementById('kv').textContent=d.videos;document.getElementById('ks').textContent=d.streams}
async function load(){if(current==='videos'){const r=await fetch('/api/videos?limit=500');const d=await r.json();document.getElementById('videoList').innerHTML=d.length?d.map(v=>'<div class="card"><b>'+esc(v.title)+'</b><span class="tag">'+esc(v.category)+'</span><br><small>'+esc(v.domain||'')+' · '+esc(v.page_url)+'</small><br><a href="/api/vod/detail?id='+v.id+'" target="_blank">查看视频与流详情</a></div>').join(''):'<div class="empty">还没有发现视频资源</div>'}
if(current==='streams'){const r=await fetch('/api/resources/streams?limit=500');const d=await r.json();document.getElementById('streamList').innerHTML=d.length?d.map(x=>'<tr><td>'+esc(x.title)+'</td><td>'+esc(x.stream_type)+'</td><td class="url">'+esc(x.url)+'</td><td class="url">'+esc(x.page_url)+'</td><td>'+esc(x.last_seen)+'</td></tr>').join(''):'<tr><td colspan="5" class="empty">还没有媒体流</td></tr>'}
if(current==='pages'){const r=await fetch('/api/resources/pages?limit=500');const d=await r.json();document.getElementById('pageList').innerHTML=d.length?d.map(x=>'<tr><td>'+esc(x.title)+'</td><td>'+x.depth+'</td><td>'+esc(x.status)+'</td><td class="url"><a href="'+esc(x.url)+'" target="_blank">'+esc(x.url)+'</a></td><td>'+esc(x.last_seen)+'</td><td>'+esc(x.error)+'</td></tr>').join(''):'<tr><td colspan="6" class="empty">还没有爬取页面</td></tr>'}}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
load();status();setInterval(status,1000);setInterval(load,3000);
</script></body></html>"""

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
    crawl_task=asyncio.create_task(crawler.crawl(str(req.url),max_pages=req.max_pages,max_depth=req.max_depth,delay_ms=req.delay_ms))
    return {"ok":True,"message":"已开始从该站点首页递归发现同域页面并采集视频","status":crawler.stats}

@app.post("/api/crawl/stop")
async def stop_crawl():
    crawler.stop()
    return {"ok":True,"message":"已请求停止采集","status":crawler.stats}

@app.get("/api/crawl/status")
def crawl_status():
    return {"running":crawler.running,**crawler.stats,**runtime,**crawl_summary()}

@app.get("/api/resources/pages")
def resources_pages(q:str|None=None,limit:int=Query(300,le=1000)):
    return list_crawl_pages(q,limit)

@app.get("/api/resources/streams")
def resources_streams(q:str|None=None,limit:int=Query(300,le=1000)):
    return list_streams(q,limit)

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
