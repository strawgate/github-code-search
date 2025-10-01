GitHub Code Search MCP Server

Overview
This project provides a Model Context Protocol (MCP) server that can shallow‑clone public GitHub repositories and perform high‑performance code search using ripgrep. It exposes typed tools for retrieving files, searching code, and listing files, suitable for integration with MCP clients.

Features
- Shallow clone repositories (depth=1) for fast, low‑bandwidth operation
- Search code with ripgrep patterns, globs, type filters, and context lines
- Retrieve individual files with optional line truncation
- List files by globs and type filters
- Structured, typed results (Pydantic v2 models)

Requirements
- Python >= 3.12
- Network access to GitHub for cloning

Installation
- Using uv:
  ```bash
  uv venv && source .venv/bin/activate
  uv pip install -e .[dev]
  ```

Configuration
- Environment variables:
  - CLONE_DIR: Directory where shallow clones are created. Defaults to `<cwd>/temp`.

Exposed MCP tools
Currently registered tools:
- get_file(owner, repo, path, truncate_lines=100) -> File
- get_files(owner, repo, paths[list], truncate_lines=100) -> list[File]
- search_code(owner, repo, patterns[list[str]], include_globs[list[str]]|None, exclude_globs[list[str]]|None, include_types[list[str]]|None, exclude_types[list[str]]|None, max_results=30) -> list[FileWithMatches]

License
MIT