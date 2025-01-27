from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel
import aiohttp
from loguru import logger
from app.models.config import GiteaConfig

class CommitDiff(BaseModel):
    commit_id: str
    commit_message: str
    files: List[dict]  # 包含每个文件的变更信息
    diff_content: str  # commit 的完整 diff 内容

class ReviewComment(BaseModel):
    path: str
    line: int
    body: str
    commit_id: str

class SCMProvider(ABC):
    @abstractmethod
    async def get_diff(self, owner: str, repo: str, pr_id: str) -> List[CommitDiff]:
        pass

    @abstractmethod
    async def post_comment(self, owner: str, repo: str, pr_id: str, comments: List[ReviewComment]):
        pass

    @abstractmethod
    async def approve_pr(self, owner: str, repo: str, pr_id: str):
        """批准PR"""
        pass

    @abstractmethod
    async def merge_pr(self, owner: str, repo: str, pr_id: str):
        pass

    @abstractmethod
    async def get_file_context(self, owner: str, repo: str, file_path: str, commit_id: str, line_start: int, line_count: int) -> str:
        pass

class GiteaClient(SCMProvider):
    def __init__(self, config: GiteaConfig):
        self.config = config
        self.headers = {
            "Authorization": f"token {config.token}",
            "Content-Type": "application/json"
        }
        logger.info("GiteaClient initialized with URL: {}", config.url)

    async def _make_request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.config.url}/api/v1/{path}"
        logger.debug("Making {} request to {}", method, url)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=self.headers, **kwargs) as response:
                    response.raise_for_status()
                    data = await response.json()
                    logger.debug("Request successful: {} {}", method, url)
                    return data
        except Exception as e:
            logger.error("Request failed: {} {} - {}", method, url, str(e))
            raise

    async def get_diff(self, owner: str, repo: str, pr_id: str) -> List[CommitDiff]:
        logger.info("Getting diff for PR {}/{} #{}", owner, repo, pr_id)
        try:
            # 获取PR的所有commits
            commits = await self._make_request(
                "GET",
                f"repos/{owner}/{repo}/pulls/{pr_id}/commits"
            )
            
            diffs = []
            for commit in commits:
                commit_id = commit["sha"]
                
                # 获取这个commit的完整diff
                async with aiohttp.ClientSession() as session:
                    url = f"{self.config.url}/api/v1/repos/{owner}/{repo}/git/commits/{commit_id}.diff"
                    async with session.get(url, headers=self.headers) as response:
                        response.raise_for_status()
                        diff_content = await response.text()
                
                # 获取这个commit变更的文件列表
                files = await self._make_request(
                    "GET",
                    f"repos/{owner}/{repo}/git/commits/{commit_id}"
                )
                
                diffs.append(CommitDiff(
                    commit_id=commit_id,
                    commit_message=commit["commit"]["message"],
                    files=files.get("files", []),
                    diff_content=diff_content
                ))
            
            logger.info("Found {} commits in PR {}/{} #{}", 
                       len(diffs), owner, repo, pr_id)
            return diffs
        except Exception as e:
            logger.error("Failed to get diff for PR {}/{} #{}: {}", 
                        owner, repo, pr_id, str(e))
            raise

    async def post_comment(self, owner: str, repo: str, pr_id: str, comments: List[ReviewComment]):
        logger.info("Posting {} comments to PR {}/{} #{}", 
                   len(comments), owner, repo, pr_id)
        if not comments:
            return
            
        review_comments = []
        for comment in comments:
            review_comments.append({
                "path": comment.path,
                "body": comment.body,
                "new_position": comment.line,
                "commit_id": comment.commit_id
            })
            
        try:
            await self._make_request(
                "POST",
                f"repos/{owner}/{repo}/pulls/{pr_id}/reviews",
                json={
                    "commit_id": comments[0].commit_id,
                    "body": "Code Review Comments",
                    "comments": review_comments,
                    "event": "comment"
                }
            )
            logger.info("Successfully posted comments to PR {}/{} #{}", 
                       owner, repo, pr_id)
        except Exception as e:
            logger.error("Failed to post comments to PR {}/{} #{}: {}", 
                        owner, repo, pr_id, str(e))
            raise

    async def approve_pr(self, owner: str, repo: str, pr_id: str):
        """批准PR"""
        logger.info("Approving PR {}/{} #{}", owner, repo, pr_id)
        try:
            await self._make_request(
                "POST",
                f"repos/{owner}/{repo}/pulls/{pr_id}/reviews",
                json={
                    "body": "LGTM! 代码评审通过。",
                    "event": "APPROVE"
                }
            )
            logger.info("Successfully approved PR {}/{} #{}", owner, repo, pr_id)
        except Exception as e:
            logger.error("Failed to approve PR {}/{} #{}: {}", 
                        owner, repo, pr_id, str(e))
            raise

    async def merge_pr(self, owner: str, repo: str, pr_id: str):
        logger.info("Attempting to merge PR {}/{} #{}", owner, repo, pr_id)
        try:
            await self._make_request(
                "POST", 
                f"repos/{owner}/{repo}/pulls/{pr_id}/merge",
                json={
                    "Do": "merge",  # 合并方式：merge, rebase, squash, rebase-merge
                    "merge_message_field": "",  # 可选的合并信息
                    "merge_title_field": "",    # 可选的合并标题
                    "force_merge": False        # 是否强制合并
                }
            )
            logger.info("Successfully merged PR {}/{} #{}", owner, repo, pr_id)
        except Exception as e:
            logger.error("Failed to merge PR {}/{} #{}: {}", 
                        owner, repo, pr_id, str(e))
            raise

    async def get_file_context(self, owner: str, repo: str, file_path: str, commit_id: str, line_start: int, line_count: int) -> str:
        logger.debug("Getting file context for {}/{} {} @ {}", 
                    owner, repo, file_path, commit_id)
        try:
            # 使用raw内容API直接获取文件内容
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.url}/api/v1/repos/{owner}/{repo}/raw/{file_path}?ref={commit_id}",
                    headers=self.headers
                ) as response:
                    response.raise_for_status()
                    content = await response.text()
                    
            lines = content.splitlines()
            start = max(0, line_start - line_count)
            end = min(len(lines), line_start + line_count)
            
            context = "\n".join(lines[start:end])
            logger.debug("Got {} lines of context for {}", len(context.splitlines()), file_path)
            return context
        except Exception as e:
            logger.error("Failed to get file context for {}: {}", file_path, str(e))
            return ""  # 如果获取上下文失败，返回空字符串 