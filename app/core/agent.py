from typing import List, Dict, Any, Optional
from app.models.config import AppConfig
from app.services.llm_service import LLMService, CodeContext, ReviewResult, QualityMetrics
from app.core.scm import SCMProvider, CommitDiff, ReviewComment
from loguru import logger
import fnmatch
import os

class CodeReviewAgent:
    def __init__(self, config: AppConfig, scm: SCMProvider, llm: LLMService) -> None:
        self.config = config
        self.scm = scm
        self.llm = llm
        logger.info("CodeReviewAgent initialized with model: {} and config: {}", config.llm.model, config.dict())

    def _filter_files(self, files: List[dict]) -> List[dict]:
        """过滤不需要评审的文件"""
        filtered = []
        for file in files:
            should_ignore = any(
                fnmatch.fnmatch(file["filename"], pattern)
                for pattern in self.config.review.ignore_patterns
            )
            if not should_ignore:
                filtered.append(file)
        return filtered

    async def _collect_context(self, owner: str, repo: str, commit_diff: CommitDiff) -> Optional[CodeContext]:
        # 过滤文件
        filtered_files = self._filter_files(commit_diff.files)
        if not filtered_files:
            logger.info("No files to review after filtering for commit {} (changed files: {})", 
                        commit_diff.commit_id[:8], len(commit_diff.files))
            return None
            
        # 收集所有文件的上下文
        files_context = []
        window_size = self.config.scm.context_window
        
        for file in filtered_files:
            if "filename" not in file:
                logger.error("Invalid file data - missing filename in commit: {}", commit_diff.commit_id[:8])
                continue
                
            file_path = file["filename"]
            file_type = os.path.splitext(file_path)[1][1:] if os.path.splitext(file_path)[1] else "unknown"
            
            try:
                # 获取文件上下文
                context = await self.scm.get_file_context(
                    owner,
                    repo,
                    file_path,
                    commit_diff.commit_id,
                    1,
                    window_size * 2
                )
                
                if not context:
                    logger.warning("No context returned for file: {} in commit: {}", file_path, commit_diff.commit_id[:8])
                    continue
                    
                files_context.append({
                    "file_path": file_path,
                    "file_type": file_type,
                    "context": context
                })
            except Exception as e:
                logger.error("Error getting context for file {} in commit {}: {}", 
                             file_path, commit_diff.commit_id[:8], str(e))
                continue
                
        if not files_context:
            logger.warning("No valid file contexts collected for commit {} (total files: {})", 
                           commit_diff.commit_id[:8] if commit_diff and commit_diff.commit_id else "unknown", 
                           len(commit_diff.files) if commit_diff and hasattr(commit_diff, 'files') else 0)
            return None
            
        # 创建并验证上下文对象
        try:
            context = CodeContext(
                diff=commit_diff.diff_content,
                files_context=files_context,
                metadata={
                    "commit_id": commit_diff.commit_id,
                    "commit_message": commit_diff.commit_message
                }
            )
            return context
        except Exception as e:
            logger.error("Error creating CodeContext for commit {}: {}", 
                         commit_diff.commit_id[:8] if commit_diff and commit_diff.commit_id else "unknown", 
                         str(e))
            return None

    async def _analyze_code(self, context: CodeContext) -> ReviewResult:
        """分析整个commit的代码变更"""
        logger.debug("Analyzing commit: {} - {} (files: {})",
                    context.metadata["commit_id"][:8], 
                    context.metadata["commit_message"].split('\n')[0][:50],
                    len(context.files_context))
        
        try:
            result = await self.llm.analyze_code(context)
            
            # 记录评审结果
            logger.info("Code analysis completed for commit {} with scores and {} files:",
                       context.metadata["commit_id"][:8], len(context.files_context))
            logger.info("- Overall Score: {}/10 (weight: {})", result.score, self.config.review.quality_threshold)
            logger.info("- Security: {}/10 (weight: {})", result.quality_metrics.security_score, self.config.review.scoring_rules["security"])
            logger.info("- Performance: {}/10 (weight: {})", result.quality_metrics.performance_score, self.config.review.scoring_rules["performance"])
            logger.info("- Readability: {}/10 (weight: {})", result.quality_metrics.readability_score, self.config.review.scoring_rules["readability"])
            logger.info("- Best Practices: {}/10 (weight: {})", result.quality_metrics.best_practice_score, self.config.review.scoring_rules["best_practice"])
            
            if result.security_issues:
                logger.warning("Found {} security issues in commit {} (threshold: {})",
                             len(result.security_issues), context.metadata["commit_id"][:8], self.config.review.max_security_issues)
            
            return result
        except Exception as e:
            logger.error("Error analyzing code for commit {}: {}\nFull error: {}", 
                         context.metadata.get("commit_id", "unknown")[:8], 
                         str(e), repr(e))
            # 返回一个默认的评审结果
            return ReviewResult(
                score=0,
                comments=["代码评审过程中发生错误"],
                suggestions=[],
                issues=[],
                security_issues=[],
                quality_metrics=QualityMetrics(
                    security_score=0,
                    performance_score=0,
                    readability_score=0,
                    best_practice_score=0
                )
            )

    def _generate_comments(self, result: ReviewResult, context: CodeContext) -> List[ReviewComment]:
        """生成评审评论"""
        logger.debug("Generating comments for commit: {} with {} issues", 
                     context.metadata["commit_id"][:8], len(result.issues))
        comments = []
        
        # 添加总体评分评论
        overall_comment = [
            "# 🔍 代码评审报告",
            "",
            f"## 📊 评分概览 ({result.score:.1f}/10)",
            "",
            "| 评审维度 | 得分 | 权重 |",
            "|---------|------|------|",
            f"| 🛡️ 安全性 | {result.quality_metrics.security_score:.1f}/10 | {self.config.review.scoring_rules['security']:.0f} |",
            f"| ⚡ 性能 | {result.quality_metrics.performance_score:.1f}/10 | {self.config.review.scoring_rules['performance']:.0f} |",
            f"| 📖 可读性 | {result.quality_metrics.readability_score:.1f}/10 | {self.config.review.scoring_rules['readability']:.0f} |",
            f"| ✨ 最佳实践 | {result.quality_metrics.best_practice_score:.1f}/10 | {self.config.review.scoring_rules['best_practice']:.0f} |",
            ""
        ]
        
        if result.issues:
            overall_comment.extend([
                "## 💡 需要改进的地方",
                ""
            ])
            for issue in result.issues:
                overall_comment.extend([
                    f"### {issue.file_path}",
                    f"- 位置：第{issue.start_line}行" + (f"-{issue.end_line}行" if issue.end_line else ""),
                    f"- 问题：{issue.description}",
                    f"- 建议：{issue.suggestion}",
                    ""
                ])
        
        if result.security_issues:
            overall_comment.extend([
                "## ⚠️ 安全问题",
                ""
            ])
            for issue in result.security_issues:
                severity_icon = "🔴" if issue.severity.lower() == "high" else "🟡"
                overall_comment.extend([
                    f"### {severity_icon} {issue.file_path}",
                    f"- 严重程度：{issue.severity}",
                    f"- 位置：第{issue.start_line}行" + (f"-{issue.end_line}行" if issue.end_line else ""),
                    f"- 问题：{issue.description}",
                    f"- 建议：{issue.suggestion}",
                    ""
                ])
        
        comments.append(ReviewComment(
            path=context.metadata["commit_message"],
            line=1,
            body="\n".join(overall_comment),
            commit_id=context.metadata["commit_id"]
        ))
        
        logger.info("Generated {} review comments for commit {}", 
                    len(comments), context.metadata["commit_id"][:8])
        return comments

    async def review_pr(self, owner: str, repo: str, pr_id: str) -> bool:
        """执行PR评审的主流程"""
        logger.info("Starting PR review for {}/{} #{}", 
                    owner, repo, pr_id)
        try:
            # 获取PR的所有commits及其diff
            commit_diffs = await self.scm.get_diff(owner, repo, pr_id)
            logger.info("Found {} commits to review in PR {}/{} #{}", 
                        len(commit_diffs), owner, repo, pr_id)
            
            all_results = []
            for commit_diff in commit_diffs:
                try:
                    logger.info("Reviewing commit: {} - {} (files: {})",
                               commit_diff.commit_id[:8],
                               commit_diff.commit_message.split('\n')[0][:50],
                               len(commit_diff.files))
                    
                    # 收集整个commit的上下文
                    context = await self._collect_context(owner, repo, commit_diff)
                    if not context:
                        logger.warning("Skipping commit {} due to no reviewable files (total files: {})",
                                     commit_diff.commit_id[:8], len(commit_diff.files))
                        continue
                    
                    # 分析整个commit的代码
                    result = await self._analyze_code(context)
                    all_results.append((result, context))
                    
                    # 生成并发送评论
                    comments = self._generate_comments(result, context)
                    
                    await self.scm.post_comment(owner, repo, pr_id, comments)
                    logger.info("Posted {} review comments for commit {}", 
                                len(comments), commit_diff.commit_id[:8])
                except Exception as commit_error:
                    logger.error("Error processing commit {} with {} files: {}\nFull error: {}",
                                commit_diff.commit_id[:8], len(commit_diff.files), str(commit_error), repr(commit_error))
                    continue
            
            # 处理评审结果 - 使用最低分作为最终分数
            if all_results:
                min_score = min(r.score for r, _ in all_results)
                logger.info("PR review completed with minimum score: {} (threshold: {})", 
                            min_score, self.config.review.quality_threshold)
                if min_score >= self.config.review.quality_threshold:
                    logger.info("PR quality meets threshold ({} >= {}), attempting to approve and merge",
                               min_score, self.config.review.quality_threshold)
                    # 先批准PR
                    await self.scm.approve_pr(owner, repo, pr_id)
                    # 再合并PR
                    await self.scm.merge_pr(owner, repo, pr_id)
                else:
                    logger.info("PR quality below threshold ({} < {}), skipping approval",
                               min_score, self.config.review.quality_threshold)
            
            return True
            
        except Exception as e:
            logger.error("Error reviewing PR {}/{} #{}: {}\nFull error: {}", 
                         owner, repo, pr_id, str(e), repr(e))
            return False 