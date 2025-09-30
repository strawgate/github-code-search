import os
from logging import Logger
from pathlib import Path

from fastmcp.server.server import FastMCP
from fastmcp.utilities.logging import get_logger

from github_code_search.servers.repository import RepositoryServer

clone_dir = Path(os.environ.get("CLONE_DIR", Path.cwd() / "temp"))

clone_dir.mkdir(parents=True, exist_ok=True)

mcp: FastMCP[None] = FastMCP[None](name="github-code-search")


logger: Logger = get_logger(name=__name__)

repository_server: RepositoryServer = RepositoryServer(logger=logger, clone_dir=clone_dir)

repository_server.register_tools(mcp=mcp)


if __name__ == "__main__":
    mcp.run(transport="sse")
