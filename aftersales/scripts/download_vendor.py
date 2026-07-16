"""一次性下载前端本地依赖（Vue 3 / ECharts）到 frontend/vendor/。

已随项目附带；若文件丢失或需要更新版本时运行：python scripts/download_vendor.py
"""
import urllib.request
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "frontend" / "vendor"
FILES = {
    "vue.global.prod.js": "https://unpkg.com/vue@3.4.38/dist/vue.global.prod.js",
    "echarts.min.js": "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
}

VENDOR.mkdir(parents=True, exist_ok=True)
for name, url in FILES.items():
    print(f"下载 {name} …")
    urllib.request.urlretrieve(url, VENDOR / name)
print("完成。")
