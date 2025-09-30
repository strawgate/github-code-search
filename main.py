from logging import Logger


from pathlib import Path
from fastmcp.server.server import FastMCP
from git import Repo


from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger


mcp: FastMCP[None] = FastMCP[None](name="github-code-search")

cloned_repositories: dict[str, Path] = {}

logger: Logger = get_logger(name=__name__)

def clone_github_repository(owner: str, repo: str, directory: str) -> Path:
    """Clone a git repository to a temporary directory."""
    if f"{owner}/{repo}" in cloned_repositories:
        return cloned_repositories[f"{owner}/{repo}"]
    logger.info(f"Cloning repository {owner}/{repo} to {directory}")
    _ = Repo.clone_from(
        f"https://github.com/{owner}/{repo}.git", directory, depth=1, single_branch=True
    )
    cloned_repositories[f"{owner}/{repo}"] = Path(directory)
    logger.info(f"Cloned repository {owner}/{repo} to {directory}")
    return Path(directory)


@mcp.tool()
def search_code(owner: str, repo: str, path: str) -> str:
    repo_path = clone_github_repository(owner, repo, f"{owner}/{repo}")
    file = repo_path / path
    if not file.exists():
        raise ValueError(f"File {path} not found in repository {repo}")
    return file.read_text()

if __name__ == "__main__":
    mcp.run(transport="sse")
