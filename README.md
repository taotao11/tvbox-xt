# TVBox XT：特定网站全站视频采集器

这个版本不再要求你一个页面一个页面地手动播放。输入一个你有权访问的网站首页后，程序会在**同一域名内递归发现页面**，访问详情页/分页，并监听网络媒体请求，把发现的视频流保存到 SQLite，最后通过 TVBox JSON 提供给客户端。

## 1. 安装

Windows PowerShell：

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m playwright install chromium

## 2. 启动

    python -m app.main

打开：

    http://127.0.0.1:9978

SQLite：

    data/videos.db

## 3. 全站自动采集

在管理页面输入目标网站首页，例如：

    https://example.com

然后点击“开始全站采集”。

程序会：

1. 从首页开始；
2. 只跟随同域名的 HTTP/HTTPS 页面；
3. 去除 URL fragment，避免同一页面重复；
4. 访问发现的页面；
5. 自动触发普通 HTML5 video 播放器；
6. 监听 Network Response；
7. 识别 m3u8、mp4、m4v、webm、flv、mov、ts、mpd 等媒体；
8. 按页面标题/URL 自动分类；
9. 将视频页面、站点、媒体流、请求头信息写入 SQLite；
10. 前端实时显示已访问页面和捕获数量。

### 限制采集规模

管理页面默认最多访问 1000 个页面，也可以通过 API 调整。

例如：

    POST /api/crawl

JSON：

    {
      "url": "https://example.com",
      "max_pages": 5000,
      "max_depth": 30,
      "delay_ms": 250
    }

## 4. 后台自动启动

如果希望程序启动后直接采集固定网站，可以设置：

Windows PowerShell：

    $env:SITE_URL="https://example.com"
    python -m app.main

Linux/macOS：

    SITE_URL="https://example.com" python -m app.main

默认仍然是手动输入网址。

## 5. API

    GET  /                       管理页面
    POST /api/browse             打开单个页面
    POST /api/crawl              开始全站递归采集
    POST /api/crawl/stop         停止采集
    GET  /api/crawl/status       查看采集进度
    GET  /api/videos              视频列表
    GET  /api/vod/detail?id=1    视频详情和流
    GET  /api/vod/play?id=1      播放信息
    GET  /api/tvbox               TVBox JSON

TVBox 局域网地址：

    http://电脑局域网IP:9978/api/tvbox

## 6. 当前架构

    网站首页
       ↓
    SiteCrawler
       ↓
    同域页面递归发现
       ↓
    Playwright 浏览器
       ↓
    自动触发普通视频播放器
       ↓
    Network Response
       ↓
    VideoSniffer
       ↓
    SQLite
       ↓
    /api/tvbox

## 7. 注意

项目用于你拥有或获授权访问的网站。它不实现 DRM 解密、付费墙绕过或访问控制绕过。

另外，“爬完整个网站”和“保证抓到每一个视频流”不是完全等价的：如果某些视频只有登录后、点击特定控件后或通过站点专用 JS 才会请求媒体地址，需要针对该网站增加站点适配器。这个项目现在已经把通用的全站发现、浏览、媒体监听和 SQLite/TVBox 输出链路搭好了。
