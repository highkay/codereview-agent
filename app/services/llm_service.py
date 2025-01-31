from typing import List, Dict, Optional
import tiktoken
from pydantic import BaseModel
import litellm
from loguru import logger
from app.models.config import LLMConfig, ReviewConfig

class CodeIssue(BaseModel):
    file_path: str
    start_line: int
    end_line: Optional[int]
    description: str
    suggestion: str

class SecurityIssue(BaseModel):
    severity: str
    file_path: str
    start_line: int
    end_line: Optional[int]
    description: str
    suggestion: str

class QualityMetrics(BaseModel):
    security_score: float
    performance_score: float
    readability_score: float
    best_practice_score: float

class ReviewResult(BaseModel):
    score: float
    issues: List[CodeIssue]
    security_issues: List[SecurityIssue]
    quality_metrics: QualityMetrics

class CodeContext(BaseModel):
    diff: str  # commit 的完整 diff 内容
    files_context: List[dict]  # 包含每个文件的上下文信息
    metadata: Dict[str, str]  # commit 相关的元数据

    def __len__(self) -> int:
        """返回文件上下文的数量"""
        return len(self.files_context)

REVIEW_PROMPT = """你是一个专业的代码评审专家，请根据以下代码变更内容进行评审。评审时请特别注意以下几点：

1. 安全性（占比30%）：
   - 检查SQL注入、XSS等安全漏洞
   - 检查敏感信息泄露
   - 检查权限控制问题
   
2. 性能（占比20%）：
   - 检查算法复杂度
   - 检查资源使用效率
   - 检查并发处理方式
   
3. 可读性（占比20%）：
   - 代码格式是否规范
   - 命名是否清晰
   - 注释是否充分
   
4. 最佳实践（占比30%）：
   - 是否遵循设计模式
   - 是否有单元测试
   - 是否有类型提示
   - 是否符合SOLID原则

评分规则：
- 安全问题：高危-3分/个，中危-1分/个
- 性能问题：-2分/个
- 可读性问题：-0.5分/个
- 最佳实践：缺少单元测试-2分，无类型提示-1分

Commit信息：
{commit_message}

代码变更：
{diff}

相关文件上下文：
{files_context}

请提供详细的评审结果，包括：
1. 总体评分（满分10分）
2. 具体问题列表（包含文件路径和代码位置）
3. 安全问题清单（包含文件路径和代码位置）
4. 各维度的具体评分

请以JSON格式返回结果，格式如下：
{{
    "score": float,
    "issues": [
        {{
            "file_path": string,
            "start_line": int,
            "end_line": int | null,
            "description": string,
            "suggestion": string
        }}
    ],
    "security_issues": [
        {{
            "severity": string,
            "file_path": string,
            "start_line": int,
            "end_line": int | null,
            "description": string,
            "suggestion": string
        }}
    ],
    "quality_metrics": {{
        "security_score": float,
        "performance_score": float,
        "readability_score": float,
        "best_practice_score": float
    }}
}}

注意：
1. 每个问题必须指明具体的文件路径和代码位置（行号）
2. 如果问题涉及多行代码，请提供start_line和end_line
3. 如果问题只涉及单行代码，end_line可以为null
4. 所有的行号必须是实际的代码行号
"""

class LLMService:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.model_name = config.model
        self.api_key = config.api_key
        
        if not self.model_name:
            raise ValueError("Model name is required")
        if not self.api_key:
            raise ValueError("API key is required")
            
        logger.info("Setting up LLMService with model: {} and max_tokens: {}", 
                    self.model_name if hasattr(self, 'model_name') else "unknown", 
                    self.config.max_tokens if hasattr(self, 'config') and hasattr(self.config, 'max_tokens') else 0)
        litellm.api_key = self.api_key
        litellm.set_verbose = False
        
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4")
            logger.info("Tokenizer initialized successfully for model: {}", 
                        self.model_name if hasattr(self, 'model_name') else "unknown")
        except Exception as e:
            logger.error("Error initializing tokenizer for model {}: {}", 
                         self.model_name if hasattr(self, 'model_name') else "unknown", 
                         str(e))
            raise
            
        logger.info("LLMService initialized successfully with model: {} and chunk_size: {}", 
                    self.model_name if hasattr(self, 'model_name') else "unknown", 
                    self.config.max_tokens if hasattr(self, 'config') and hasattr(self.config, 'max_tokens') else 0)
    
    def _split_code_chunks(self, context: CodeContext) -> List[CodeContext]:
        max_tokens = self.config.max_tokens - 1000  # 预留空间给prompt和response
        
        def count_tokens(text: str) -> int:
            return len(self.tokenizer.encode(text))

        chunks = []
        current_chunk = CodeContext(
            diff="",
            files_context=[],
            metadata=context.metadata
        )
        current_tokens = 0
        
        # 按文件分割diff内容
        diff_content = context.diff
        file_diffs = diff_content.split("diff --git ")
        if file_diffs[0] == "":  # 移除空的第一个元素
            file_diffs = file_diffs[1:]
            
        current_files = []  # 当前chunk包含的文件路径
        
        for file_diff in file_diffs:
            if not file_diff:
                continue
                
            file_diff = "diff --git " + file_diff
            file_tokens = count_tokens(file_diff)
            
            # 从diff中提取文件路径
            import re
            file_path_match = re.search(r'a/(.*?) b/', file_diff)
            if not file_path_match:
                continue
            file_path = file_path_match.group(1)
            
            if current_tokens + file_tokens > max_tokens and current_chunk.diff:
                # 添加相关的文件上下文
                current_chunk.files_context = [
                    f for f in context.files_context 
                    if f["file_path"] in current_files
                ]
                chunks.append(current_chunk)
                
                # 重置当前chunk
                current_chunk = CodeContext(
                    diff="",
                    files_context=[],
                    metadata=context.metadata
                )
                current_tokens = 0
                current_files = []
            
            # 添加文件diff到当前chunk
            current_chunk.diff += file_diff
            current_tokens += file_tokens
            current_files.append(file_path)
        
        # 处理最后一个chunk
        if current_chunk.diff:
            current_chunk.files_context = [
                f for f in context.files_context 
                if f["file_path"] in current_files
            ]
            chunks.append(current_chunk)
        
        logger.info("Split code into {} chunks with total size: {} characters", 
                    len(chunks) if chunks else 0, 
                    sum(len(chunk.diff) if hasattr(chunk, 'diff') else 0 for chunk in chunks) if chunks else 0)
        return chunks

    async def analyze_code(self, context: CodeContext) -> ReviewResult:
        chunks = self._split_code_chunks(context)
        results = []
        
        for i, chunk in enumerate(chunks):
            logger.info("Analyzing chunk {}/{} with size: {} characters", 
                        i + 1, len(chunks) if chunks else 0, 
                        len(chunk.diff) if hasattr(chunk, 'diff') else 0)
            
            # 格式化文件上下文
            files_context_str = "\n\n".join(
                f"文件: {f['file_path']} ({f['file_type']})\n{f['context']}"
                for f in chunk.files_context
            ) if chunk.files_context else "无文件上下文"
            
            # 验证必需的参数
            if not context.metadata.get("commit_message"):
                logger.error("Missing commit message in metadata for commit: {}", 
                             context.metadata.get("commit_id", "unknown")[:8] if context and hasattr(context, 'metadata') else "unknown")
                raise ValueError("Missing commit message in metadata")
                
            if not chunk.diff:
                logger.error("Missing diff content for commit: {}", 
                             context.metadata.get("commit_id", "unknown")[:8] if context and hasattr(context, 'metadata') else "unknown")
                raise ValueError("Missing diff content")
            
            try:
                prompt = REVIEW_PROMPT.format(
                    commit_message=context.metadata["commit_message"],
                    diff=chunk.diff,
                    files_context=files_context_str
                )
            except KeyError as ke:
                logger.error("Error formatting prompt - missing key: {}", ke)
                raise ValueError(f"Missing required field for prompt formatting: {ke}")
            except Exception as e:
                logger.error("Error formatting prompt: {}", str(e))
                raise ValueError(f"Failed to format prompt: {str(e)}")
                
            if not prompt:
                logger.error("Empty prompt after formatting")
                raise ValueError("Empty prompt after formatting")
            
            try:
                logger.info("Sending request to LLM model: {} with prompt size: {} characters", 
                            self.model_name if hasattr(self, 'model_name') else "unknown", 
                            len(prompt) if prompt else 0)
                
                try:
                    response = await litellm.acompletion(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2
                    )
                    logger.info("Received response from LLM with size: {} characters", 
                                len(str(response)) if response else 0)
                    
                    if not response or not hasattr(response, 'choices') or not response.choices:
                        logger.error("Invalid response format from LLM. Expected JSON, got: {}", 
                                     type(response).__name__ if response else "None")
                        raise ValueError("Invalid response format from LLM")
                        
                    response_text = response.choices[0].message.content
                except Exception as llm_error:
                    logger.error("Error calling LLM model {}: {}", 
                                 self.model_name if hasattr(self, 'model_name') else "unknown", 
                                 str(llm_error))
                    raise
                
                response_text = response_text.strip()
                
                # 查找JSON内容的开始和结束位置
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                
                if json_start == -1 or json_end <= json_start:
                    logger.error("No valid JSON found in response of size: {} characters", 
                                 len(str(response)) if response else 0)
                    # 返回默认结果而不是抛出异常
                    return ReviewResult(
                        score=0,
                        issues=[],
                        security_issues=[],
                        quality_metrics=QualityMetrics(
                            security_score=0,
                            performance_score=0,
                            readability_score=0,
                            best_practice_score=0
                        )
                    )
                
                response_text = response_text[json_start:json_end]
                
                try:
                    import json
                    # 尝试清理和格式化 JSON 字符串
                    response_text = response_text.replace('\n', ' ').replace('\r', '')
                    # 处理可能的 markdown 代码块
                    if '```json' in response_text:
                        response_text = response_text.split('```json')[-1].split('```')[0]
                    elif '```' in response_text:
                        response_text = response_text.split('```')[-2]
                    
                    # 先尝试解析JSON
                    json_obj = json.loads(response_text)
                    
                    # 确保所有必需的字段都存在并且类型正确
                    required_fields = {
                        "score": float,
                        "issues": list,
                        "security_issues": list,
                        "quality_metrics": dict
                    }
                    
                    for field, field_type in required_fields.items():
                        if field not in json_obj:
                            logger.warning("Missing required field: {} in response for commit: {}, adding default value", 
                                           field, context.metadata.get("commit_id", "unknown")[:8] if context and hasattr(context, 'metadata') else "unknown")
                            if field == "issues":
                                json_obj["issues"] = []
                            elif field == "security_issues":
                                json_obj["security_issues"] = []
                            elif field == "quality_metrics":
                                json_obj["quality_metrics"] = {
                                    "security_score": 0.0,
                                    "performance_score": 0.0,
                                    "readability_score": 0.0,
                                    "best_practice_score": 0.0
                                }
                            elif field == "score":
                                json_obj["score"] = 0.0
                        elif not isinstance(json_obj[field], field_type):
                            logger.warning("Field {} has wrong type. Expected {}, got {}. Converting to default value.", 
                                           field, field_type.__name__ if hasattr(field_type, '__name__') else str(field_type), 
                                           type(json_obj[field]).__name__ if json_obj and field in json_obj else "unknown")
                            if field == "issues":
                                json_obj["issues"] = []
                            elif field == "security_issues":
                                json_obj["security_issues"] = []
                            elif field == "quality_metrics":
                                json_obj["quality_metrics"] = {
                                    "security_score": 0.0,
                                    "performance_score": 0.0,
                                    "readability_score": 0.0,
                                    "best_practice_score": 0.0
                                }
                            elif field == "score":
                                json_obj["score"] = 0.0
                    
                    # 检查 quality_metrics 的字段
                    required_metrics = {
                        "security_score": float,
                        "performance_score": float,
                        "readability_score": float,
                        "best_practice_score": float
                    }
                    
                    if "quality_metrics" in json_obj:
                        for metric, metric_type in required_metrics.items():
                            if metric not in json_obj["quality_metrics"]:
                                logger.warning("Missing required metric: {} in quality metrics for commit: {}, adding default value", 
                                               metric, context.metadata.get("commit_id", "unknown")[:8] if context and hasattr(context, 'metadata') else "unknown")
                                json_obj["quality_metrics"][metric] = 0.0
                            elif not isinstance(json_obj["quality_metrics"][metric], metric_type):
                                json_obj["quality_metrics"][metric] = float(json_obj["quality_metrics"][metric])
                    
                    result = ReviewResult.parse_obj(json_obj)
                    results.append(result)
                    logger.info("Successfully analyzed chunk {}/{} for commit: {}", 
                                i + 1, len(chunks) if chunks else 0, 
                                context.metadata.get("commit_id", "unknown")[:8] if context and hasattr(context, 'metadata') else "unknown")
                except json.JSONDecodeError as json_error:
                    logger.error("JSON parsing error at position {} in response of size {}: {}", 
                                 getattr(json_error, 'pos', 0), 
                                 len(str(response)) if response else 0, 
                                 str(json_error))
                    raise
                except Exception as parse_error:
                    logger.error("Error parsing LLM response of size {}: {}", 
                                 len(str(response)) if response else 0, 
                                 str(parse_error))
                    # 返回一个默认的评审结果
                    results.append(ReviewResult(
                        score=0,
                        issues=[],
                        security_issues=[],
                        quality_metrics=QualityMetrics(
                            security_score=0,
                            performance_score=0,
                            readability_score=0,
                            best_practice_score=0
                        )
                    ))
            except Exception as e:
                logger.error("Error getting LLM response for model {}: {}", 
                             self.model_name if hasattr(self, 'model_name') else "unknown", 
                             str(e))
                raise
        
        # 合并所有chunk的结果
        if not results:
            logger.warning("No valid results for commit: {} in model: {}", 
                           context.metadata.get("commit_id", "unknown")[:8] if context and hasattr(context, 'metadata') else "unknown", 
                           self.model_name if hasattr(self, 'model_name') else "unknown")
            return ReviewResult(
                score=0,
                issues=[],
                security_issues=[],
                quality_metrics=QualityMetrics(
                    security_score=0,
                    performance_score=0,
                    readability_score=0,
                    best_practice_score=0
                )
            )
        
        # 使用最低分作为最终分数
        final_result = ReviewResult(
            score=min(r.score for r in results),
            issues=[i for r in results for i in r.issues],
            security_issues=[i for r in results for i in r.security_issues],
            quality_metrics=QualityMetrics(
                security_score=min(r.quality_metrics.security_score for r in results),
                performance_score=min(r.quality_metrics.performance_score for r in results),
                readability_score=min(r.quality_metrics.readability_score for r in results),
                best_practice_score=min(r.quality_metrics.best_practice_score for r in results)
            )
        )
        
        logger.info("Analysis completed for commit {} with final score: {}", 
                    context.metadata.get("commit_id", "unknown")[:8] if context and hasattr(context, 'metadata') else "unknown", 
                    final_result.score if final_result and hasattr(final_result, 'score') else 0.0)
        return final_result 