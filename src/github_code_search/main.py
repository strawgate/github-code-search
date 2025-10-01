import os
from logging import Logger
from pathlib import Path

from fastmcp.server.middleware.logging import LoggingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.server.server import FastMCP
from fastmcp.utilities.logging import get_logger

from github_code_search.servers.repository import RepositoryServer

clone_dir = Path(os.environ.get("CLONE_DIR", Path.cwd() / "temp"))

clone_dir.mkdir(parents=True, exist_ok=True)

logging_middleware: LoggingMiddleware = LoggingMiddleware(include_payloads=True, include_payload_length=True, estimate_payload_tokens=True)
timing_middleware: TimingMiddleware = TimingMiddleware()

mcp: FastMCP[None] = FastMCP[None](name="github-code-search", middleware=[logging_middleware, timing_middleware])

logger: Logger = get_logger(name=__name__)

repository_server: RepositoryServer = RepositoryServer(logger=logger, clone_dir=clone_dir)

repository_server.register_tools(mcp=mcp)


def run_mcp():
    mcp.run(transport="sse")


if __name__ == "__main__":
    run_mcp()
