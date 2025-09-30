from logging import Logger


import os
from pathlib import Path
from tempfile import mkdtemp
from fastmcp.server.server import FastMCP
from git import Repo


from fastmcp.utilities.logging import get_logger

clone_dir = Path(os.environ.get("CLONE_DIR", Path.cwd() / "temp"))

clone_dir.mkdir(parents=True, exist_ok=True)

mcp: FastMCP[None] = FastMCP[None](name="github-code-search")

cloned_repositories: dict[str, Path] = {}

logger: Logger = get_logger(name=__name__)


def clone_github_repository(owner: str, repo: str, directory: str) -> Path:
    """Clone a git repository to a temporary directory."""
    directory = mkdtemp(prefix=f"{owner}_{repo}", dir=clone_dir)

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
