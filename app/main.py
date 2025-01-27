import os
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import webhooks, config_ui
import uvicorn

app = FastAPI(
    title="代码评审Agent",
    description="自动代码评审系统",
    version="1.0.0"
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 注册路由
app.include_router(webhooks.router, tags=["webhooks"])
app.include_router(config_ui.router, tags=["config"])

@app.get("/")
async def root():
    """重定向到配置页面"""
    return {"message": "Welcome to Code Review Agent"}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    ) 