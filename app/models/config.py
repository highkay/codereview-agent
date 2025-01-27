from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Optional

class GiteaConfig(BaseModel):
    model_config = ConfigDict(title="Gitea配置")
    url: str = Field(description="Gitea服务器URL")
    token: str = Field(description="Gitea API访问令牌")
    context_window: int = Field(10, description="代码上下文窗口大小")

class LLMConfig(BaseModel):
    model_config = ConfigDict(title="LLM配置")
    model: str = Field("deepseek/deepseek-chat", description="模型名称")
    api_key: str = Field(description="API密钥")
    max_tokens: int = Field(60000, description="最大token数")

class ReviewConfig(BaseModel):
    model_config = ConfigDict(title="评审配置")
    quality_threshold: float = Field(8.5, description="质量阈值分数")
    max_security_issues: int = Field(5, description="最大安全问题数量")
    ignore_patterns: List[str] = Field(
        default=[
            '**/node_modules/', '**/vendor/', '**/venv/', '**/.venv/',
            '**/bower_components/', '**/jspm_packages/', '**/packages/',
            '**/deps/', '**/dist/', '**/build/', '**/out/', '**/target/',
            '**/bin/', '**/obj/', '**/*.exe', '**/*.dll', '**/*.so',
            '**/*.a', '**/*.jar', '**/*.class', '**/*.pyc',
            '**/__pycache__/', '**/*.egg-info/', '**/.DS_Store',
            '**/Thumbs.db', '**/Desktop.ini', '**/.idea/', '**/.vscode/',
            '**/.vs/', '**/*.suo', '**/*.user', '**/*.sublime-project',
            '**/*.sublime-workspace', '**/*.log', '**/logs/', '**/tmp/',
            '**/*.tmp', '**/*.swp', '**/*.swo', '**/.sass-cache/',
            '**/coverage/', '**/.nyc_output/', '**/junit.xml',
            '**/test-results/', '**/*.min.js', '**/*.min.css', '**/*.map',
            '**/public/static/', '**/compiled/', '**/generated/', '**/.env',
            '**/.env.local', '**/.env.*.local', '**/docker-compose.override.yml',
            '**/*.key', '**/*.pem', '**/*.crt', '**/docs/_build/',
            '**/site/', '**/.vuepress/dist/', '**/package-lock.json',
            '**/yarn.lock', '**/Gemfile.lock', '**/Podfile.lock'
        ],
        description="忽略的文件模式"
    )
    scoring_rules: Dict[str, float] = Field(
        default={
            "security": 0.3,
            "performance": 0.2,
            "readability": 0.2,
            "best_practice": 0.3
        },
        description="评分规则权重"
    )

class AppConfig(BaseModel):
    model_config = ConfigDict(title="应用配置")
    scm: GiteaConfig
    llm: LLMConfig
    review: ReviewConfig 