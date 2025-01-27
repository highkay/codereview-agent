from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.core.agent import CodeReviewAgent
from app.core.scm import GiteaClient
from app.services.llm_service import LLMService
from app.models.config import AppConfig
from app.routers.config_ui import load_config
import logging

router = APIRouter()

class PRWebhook(BaseModel):
    action: str
    number: int
    pull_request: Dict[str, Any]
    repository: Dict[str, Any]
    sender: Dict[str, Any]

async def process_pr(owner: str, repo: str, pr_id: str):
    """处理PR的后台任务"""
    try:
        # 加载配置
        config = load_config()
        
        # 初始化服务
        scm = GiteaClient(config.scm)
        llm = LLMService(config.llm)
        agent = CodeReviewAgent(config, scm, llm)
        
        # 执行评审
        await agent.review_pr(owner, repo, pr_id)
    except Exception as e:
        logger.error("Error processing PR {}/{} #{}: {}", 
                    owner if owner else "unknown", 
                    repo if repo else "unknown", 
                    pr_id if pr_id else "unknown", 
                    str(e))

@router.post("/webhook/gitea")
async def handle_webhook(
    webhook: PRWebhook,
    background_tasks: BackgroundTasks
):
    """处理Gitea webhook"""
    # 只处理PR相关事件
    if webhook.action not in ["opened", "reopened", "synchronize"]:
        return {"status": "ignored"}
    
    # 从仓库信息中获取owner和repo
    owner = webhook.repository["owner"]["username"]
    repo = webhook.repository["name"]
    
    # 添加后台任务
    background_tasks.add_task(
        process_pr,
        owner,
        repo,
        str(webhook.number)
    )
    
    return {"status": "processing"} 