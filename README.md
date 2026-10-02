# TVBox XT：通用网络视频嗅探器

## 1. 安装
Windows PowerShell：

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m playwright install chromium

## 2. 启动

    python -m app.main

打开 http://127.0.0.1:9978

SQLite 自动保存到 data/videos.db。

## 3. 使用

1. 在管理页面输入你有权访问的视频网站 URL。
2. 点击“打开并嗅探”。
3. Chromium 会打开网站。
4. 正常播放视频。
5. 程序监听 Network Response，发现 m3u8/mp4/webm/flv/mov/ts/mpd 等媒体请求后写入 SQLite。
6. 管理页面会自动刷新。

## 4. TVBox

局域网设备使用：

    http://电脑局域网IP:9978/api/tvbox

例如：

    http://192.168.1.100:9978/api/tvbox

Windows 防火墙需要允许 TCP 9978。

## 5. API

GET /                       管理页面
POST /api/browse            打开网址
GET /api/videos             视频列表
GET /api/vod/detail?id=1   详情和流
GET /api/vod/play?id=1     播放信息
GET /api/tvbox              TVBox JSON

## 6. 边界

项目只用于你拥有或获授权访问的视频源。它不实现 DRM 解密、付费墙绕过或访问控制绕过。
