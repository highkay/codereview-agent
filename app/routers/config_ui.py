from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import yaml
from pathlib import Path
from typing import List
from app.models.config import AppConfig, GiteaConfig, LLMConfig, ReviewConfig

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

CONFIG_FILE = "config.yaml"

def load_config() -> AppConfig:
    """加载配置文件"""
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
            return AppConfig.parse_obj(config_data)
    return AppConfig(
        scm=GiteaConfig(
            url="",
            token="",
            context_window=10
        ),
        llm=LLMConfig(
            model="deepseek/deepseek-chat",
            api_key="",
            max_tokens=60000
        ),
        review=ReviewConfig()  # 使用config.py中的默认值
    )

def save_config(config: AppConfig):
    """保存配置文件"""
    config_dict = config.dict()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f, allow_unicode=True)

@router.get("/config", response_class=HTMLResponse)
async def get_config(request: Request):
    """显示配置页面"""
    config = load_config()
    return templates.TemplateResponse(
        "config.html",
        {"request": request, "config": config}
    )

@router.post("/config", response_class=HTMLResponse)
async def save_config_handler(
    request: Request,
    scm_url: str = Form(alias="scm.url"),
    scm_token: str = Form(alias="scm.token"),
    scm_context_window: int = Form(alias="scm.context_window"),
    llm_model: str = Form(alias="llm.model"),
    llm_api_key: str = Form(alias="llm.api_key"),
    llm_max_tokens: int = Form(alias="llm.max_tokens"),
    review_quality_threshold: float = Form(alias="review.quality_threshold"),
    review_ignore_patterns: str = Form(alias="review.ignore_patterns"),
    review_scoring_rules_security: float = Form(alias="review.scoring_rules.security"),
    review_scoring_rules_performance: float = Form(alias="review.scoring_rules.performance"),
    review_scoring_rules_readability: float = Form(alias="review.scoring_rules.readability"),
    review_scoring_rules_best_practice: float = Form(alias="review.scoring_rules.best_practice")
):
    """保存配置"""
    config = AppConfig(
        scm=GiteaConfig(
            url=scm_url,
            token=scm_token,
            context_window=scm_context_window
        ),
        llm=LLMConfig(
            model=llm_model,
            api_key=llm_api_key,
            max_tokens=llm_max_tokens
        ),
        review=ReviewConfig(
            quality_threshold=review_quality_threshold,
            ignore_patterns=[p.strip() for p in review_ignore_patterns.split("\n") if p.strip()],
            scoring_rules={
                "security": review_scoring_rules_security,
                "performance": review_scoring_rules_performance,
                "readability": review_scoring_rules_readability,
                "best_practice": review_scoring_rules_best_practice
            }
        )
    )
    
    save_config(config)
    
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "config": config,
            "message": "配置已保存"
        },
        headers={"HX-Trigger": "configSaved"}
    ) 