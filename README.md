# 代码评审Agent

这是一个基于LLM的自动代码评审系统，可以自动对Gitea的Pull Request进行代码评审。

## 主要功能

1. 自动监听Gitea的Pull Request事件
2. 获取PR中的代码变更并进行分析
3. 使用LLM进行代码评审，包括：
   - 安全性评估
   - 性能分析
   - 代码可读性
   - 最佳实践检查
4. 自动生成评审评论
5. 支持根据评分自动合并PR

## 技术栈

- Python 3.10+
- FastAPI
- HTMX
- TailwindCSS
- LiteLLM

## 安装

1. 克隆仓库：
```bash
git clone https://github.com/highkay/codereview-agent.git
cd codereview-agent
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置系统：
   - 访问 `http://localhost:8000/config`
   - 填写必要的配置信息：
     - Gitea服务器URL和API Token
     - LLM提供商配置
     - 评审规则和阈值

## 运行

```bash
python app/main.py
```

服务将在 `http://localhost:8000` 启动。

## Gitea配置

1. 在Gitea中添加Webhook：
   - 进入仓库设置 -> Webhooks -> 添加Webhook
   - URL设置为：`http://your-server:8000/webhook/gitea`
   - 选择事件：Pull Request

## 评审规则

系统使用以下维度进行代码评审：

1. 安全性（30%）：
   - SQL注入
   - XSS漏洞
   - 敏感信息泄露
   - 权限控制

2. 性能（20%）：
   - 算法复杂度
   - 资源使用效率
   - 并发处理

3. 可读性（20%）：
   - 代码格式
   - 命名规范
   - 注释完整性

4. 最佳实践（30%）：
   - 设计模式
   - 单元测试
   - 类型提示
   - SOLID原则

## 评分规则

- 安全问题：
  - 高危：-3分/个
  - 中危：-1分/个
- 性能问题：-2分/个
- 可读性问题：-0.5分/个
- 最佳实践：
  - 缺少单元测试：-2分
  - 无类型提示：-1分

## 配置文件

系统使用YAML格式的配置文件（`config.yaml`）：

```yaml
scm:
  type: gitea
  url: https://git.example.com
  token: xxxx-xxxx
  context_window: 5

llm:
  provider: openai
  model: gpt-4-turbo
  api_key: sk-xxxx
  max_tokens: 4096

review:
  quality_threshold: 8.5
  ignore_patterns:
    - "*.md"
    - "**/test_*.py"
  scoring_rules:
    security: 0.3
    performance: 0.2
    readability: 0.2
    best_practice: 0.3
```

## 开发

1. 代码结构：
```
app/
├── core/           # 核心功能
│   ├── agent.py    # 评审Agent
│   └── scm.py      # SCM抽象层
├── models/         # 数据模型
│   └── config.py   # 配置模型
├── routers/        # API路由
│   ├── webhooks.py # Webhook处理
│   └── config_ui.py# 配置界面
├── services/       # 服务
│   └── llm_service.py # LLM服务
├── static/         # 静态资源
├── templates/      # 模板
│   └── config.html # 配置页面
└── main.py         # 应用入口
```

2. 添加新功能：
   - 在相应模块中添加代码
   - 确保添加适当的测试
   - 遵循项目的代码风格

## 贡献

欢迎提交Pull Request！在提交之前，请确保：

1. 代码通过所有测试
2. 添加了必要的文档
3. 遵循项目的代码规范

## 许可证

MIT License 