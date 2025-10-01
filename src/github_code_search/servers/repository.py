import asyncio
from logging import Logger, getLogger
from pathlib import Path
from typing import Annotated, get_args

from anyio import mkdtemp, open_file
from fastmcp import FastMCP
from fastmcp.tools.tool import Tool
from git.repo import Repo
from pydantic import AnyHttpUrl, BaseModel, Field, RootModel, field_validator
from rpygrep import RipGrepFind, RipGrepSearch
from rpygrep.types import RIPGREP_TYPE_LIST, RipGrepContext, RipGrepSearchResult

OWNER = Annotated[str, "The owner of the repository."]
REPO = Annotated[str, "The repository name."]
BRANCH = Annotated[str, "The branch of the repository."]
PATH = Annotated[str, "The path of the file."]

TRUNCATE_LINES = Annotated[int, "The number of lines to truncate the file to."]
MAX_RESULTS = Annotated[int, "The maximum number of results to return."]

PATTERNS = Annotated[list[str], "The regular expressions to search for. For example: 'def hello_world()'"]
INCLUDE_GLOBS = Annotated[list[str], "The globs to include in the search. For example: '*.py'"]
EXCLUDE_GLOBS = Annotated[list[str], "The globs to exclude in the search. For example: '*.pyc'"]

INCLUDE_TYPES = Annotated[list[str], "The types to include in the search. For example: 'python'"]
EXCLUDE_TYPES = Annotated[
    list[str],
    (
        "The types to exclude in the search. For example: 'python'. If not provided, common types are "
        "excluded by default (binary files, lock files, etc)."
    ),
]

GET_FILES_LIMIT = 20

EXCLUDE_BINARY_TYPES: list[RIPGREP_TYPE_LIST] = [
    "avro",
    "brotli",
    "bzip2",
    "cbor",
    "flatbuffers",
    "gzip",
    "lz4",
    "lzma",
    "pdf",
    "protobuf",
    "thrift",
    "xz",
    "zstd",
]

EXCLUDE_EXTRA_TYPES: list[RIPGREP_TYPE_LIST] = [
    "lock",
    "minified",
    "jupyter",
    "log",
    "postscript",
    "svg",
    "usd",
]

DEFAULT_EXCLUDED_TYPES: list[str] = sorted(EXCLUDE_BINARY_TYPES + EXCLUDE_EXTRA_TYPES)


class RepositoryServerError(Exception):
    """Exception raised when a repository server error occurs."""

    def __init__(self, message: str):
        super().__init__(message)


class RepositoryMissingError(Exception):
    """Exception raised when a repository is not found."""

    def __init__(self, owner: str, repo: str):
        super().__init__(f"Repository {owner}/{repo} not found")


class InvalidFilePathError(Exception):
    """Exception raised when a file path is invalid."""

    def __init__(self, owner: str, repo: str, path: str):
        super().__init__(f"File path {path} is invalid for repository {owner}/{repo}")


class FileMissingError(Exception):
    """Exception raised when a file is not found in a repository."""

    def __init__(self, owner: str, repo: str, path: str):
        super().__init__(f"File {path} not found in repository {owner}/{repo}")


# class FileLines(RootModel[dict[int, str]]):
#     """Lines of a file."""

#     @classmethod
#     def from_text(cls, text: str) -> "FileLines":
#         return cls(root=dict(enumerate(text.splitlines(keepends=True))))

#     def truncate(self, truncate_lines: int) -> "FileLines":
#         if truncate_lines >= len(self.root):
#             return self
#         return self.model_copy(update={"root": dict(list(self.root.items())[:truncate_lines])})


class FileLines(RootModel[dict[int, str]]):
    root: dict[int, str] = Field(
        default_factory=dict,
        description="A set of key-value pairs where the key is the line number and the value is the line of text at that line number.",
    )

    def lines(self) -> list[str]:
        return list(self.root.values())

    def line_numbers(self) -> list[int]:
        return list(self.root.keys())

    def first(self, count: int) -> "FileLines":
        return FileLines(root=dict(list(self.root.items())[:count]))

    @classmethod
    def from_text(cls, text: str) -> "FileLines":
        return cls(root=dict(enumerate(text.splitlines(keepends=False))))


class BaseGitHubFile(BaseModel):
    """A base class for files on GitHub."""

    # owner: str
    # repo: str
    # branch: str
    # path: str
    url: AnyHttpUrl


class BasicFileInfo(BaseModel):
    """Info about a file, without the contents."""

    # owner: str
    ##repo: str
    # branch: str
    path: str
    # url: AnyHttpUrl


class File(BaseGitHubFile):
    """A file, with the contents, optionally truncated."""

    lines: FileLines
    total_lines: int
    truncated: bool

    @classmethod
    def from_text(
        cls,
        # owner: str,
        # repo: str,
        # branch: str,
        # path: str,
        url: AnyHttpUrl,
        text: str,
        truncate_lines: int | None = None,
    ) -> "File":
        file_lines: FileLines = FileLines.from_text(text)

        total_lines: int = len(file_lines.root)

        should_truncate: bool = truncate_lines is not None and total_lines > truncate_lines

        if should_truncate and truncate_lines is not None:
            file_lines = file_lines.first(count=truncate_lines)

        return File(
            # owner=owner,
            # repo=repo,
            # branch=branch,
            # path=path,
            url=url,
            lines=file_lines,
            total_lines=total_lines,
            truncated=should_truncate,
        )


class FileEntryMatch(BaseModel):
    """A match in a file entry. Please note, blank lines are excluded, you may notice "skips" in the before and after lines as a result."""

    before: FileLines = Field(default_factory=FileLines, description="The lines of text before the line")
    match: FileLines = Field(default_factory=FileLines, description="The line of text that matches the pattern")
    after: FileLines = Field(default_factory=FileLines, description="The lines of text after the line")


class FileWithMatches(BaseGitHubFile):
    """A file with matches."""

    matches: list[FileEntryMatch]


def search_result_to_file_entry_matches(
    search_result: RipGrepSearchResult, before_context: int, after_context: int
) -> list[FileEntryMatch]:
    line_context_by_line_number: dict[int, RipGrepContext] = {context.data.line_number: context for context in search_result.context}

    file_entry_matches: list[FileEntryMatch] = []

    for line_match in search_result.matches:
        if not line_match.data.lines.text:
            continue

        before_context_lines: FileLines = FileLines(root={})
        after_context_lines: FileLines = FileLines(root={})

        # Find the before context lines
        for line_number in range(line_match.data.line_number - before_context, line_match.data.line_number):
            if line := line_context_by_line_number.pop(line_number, None):  # noqa: SIM102
                if text := line.data.lines.text:  # noqa: SIM102
                    if stripped_line := text.rstrip():
                        before_context_lines.root[line_number] = stripped_line

        # Find the after context lines
        for line_number in range(line_match.data.line_number + 1, line_match.data.line_number + after_context + 1):
            if line := line_context_by_line_number.pop(line_number, None):  # noqa: SIM102
                if text := line.data.lines.text:  # noqa: SIM102
                    if stripped_line := text.rstrip():
                        after_context_lines.root[line_number] = stripped_line

        file_entry_matches.append(
            FileEntryMatch(
                before=before_context_lines,
                match=FileLines(root={line_match.data.line_number: line_match.data.lines.text.rstrip()}),
                after=after_context_lines,
            )
        )

    return file_entry_matches


def prepare_ripgrep_arguments(
    included_globs: list[str] | None,
    excluded_globs: list[str] | None,
    included_types: list[str] | None,
    excluded_types: list[str] | None,
) -> tuple[list[str], list[str], list[RIPGREP_TYPE_LIST], list[RIPGREP_TYPE_LIST]]:
    if included_globs is None:
        included_globs = []

    if excluded_globs is None:
        excluded_globs = []

    if isinstance(included_globs, str):
        included_globs = [included_globs]

    if isinstance(excluded_globs, str):
        excluded_globs = [excluded_globs]

    included_type_list: list[RIPGREP_TYPE_LIST] = []
    excluded_type_list: list[RIPGREP_TYPE_LIST] = []

    if included_types:
        included_type_list = [t for t in included_types if t in get_args(RIPGREP_TYPE_LIST)]  # pyright: ignore[reportAssignmentType]

    if excluded_types:
        excluded_type_list = [t for t in excluded_types if t in get_args(RIPGREP_TYPE_LIST)]  # pyright: ignore[reportAssignmentType]

    return included_globs, excluded_globs, included_type_list, excluded_type_list


class Directory(BaseModel):
    """A directory."""

    owner: str
    repo: str
    branch: str
    path: str
    url: AnyHttpUrl
    files: list[str]
    directories: list[str]


class LocalRepository(BaseModel):
    """A repository entry."""

    owner: str
    repo: str
    branch: str

    local_path: Path

    @field_validator("local_path")
    @classmethod
    def validate_local_path(cls, local_path: Path) -> Path:
        return local_path.resolve()

    async def get_file(self, path: str, truncate_lines: TRUNCATE_LINES | None = None) -> File:
        file_path: Path = self.validate_file_path(path)

        async with await open_file(file=file_path) as file:
            file_text: str = await file.read()

        url: AnyHttpUrl = self.generate_file_url(path)

        return File.from_text(
            # owner=self.owner,
            # repo=self.repo,
            # branch=self.branch,
            # path=path,
            url=url,
            text=file_text,
            truncate_lines=truncate_lines,
        )

    def validate_file_path(self, path: str) -> Path:
        file_path = (self.local_path / path).resolve()

        if not file_path.is_relative_to(self.local_path):
            raise InvalidFilePathError(owner=self.owner, repo=self.repo, path=path)

        if not file_path.exists():
            raise FileMissingError(owner=self.owner, repo=self.repo, path=path)

        return file_path

    def generate_blob_url(self) -> AnyHttpUrl:
        return AnyHttpUrl(f"https://github.com/{self.owner}/{self.repo}/blob/{self.branch}")

    def generate_file_url(self, path: str) -> AnyHttpUrl:
        return AnyHttpUrl(f"{self.generate_blob_url()}/{path}")

    @property
    def search_builder(self) -> RipGrepSearch:
        return RipGrepSearch(working_directory=self.local_path).add_safe_defaults()

    @property
    def find_file_builder(self) -> RipGrepFind:
        return RipGrepFind(working_directory=self.local_path).add_safe_defaults()


class RepositoryServer:
    """Server for cloning and searching repositories."""

    def __init__(self, logger: Logger, clone_dir: Path):
        self.repositories: dict[str, LocalRepository] = {}
        self.logger: Logger = logger or getLogger(__name__)
        self.clone_dir: Path = clone_dir.resolve()
        self.repository_lock: asyncio.Lock = asyncio.Lock()

    def _add_repository(self, owner: str, repo: str, branch: str, local_path: Path) -> LocalRepository:
        repository: LocalRepository = LocalRepository(owner=owner, repo=repo, branch=branch, local_path=local_path)
        self.repositories[f"{owner}/{repo}"] = repository
        return repository

    def _get_repository(self, owner: str, repo: str) -> LocalRepository | None:
        return self.repositories.get(f"{owner}/{repo}")

    def register_tools(self, mcp: FastMCP[None]):
        _ = mcp.add_tool(tool=Tool.from_function(fn=self.get_file))
        _ = mcp.add_tool(tool=Tool.from_function(fn=self.get_files))
        _ = mcp.add_tool(tool=Tool.from_function(fn=self.find_files))
        _ = mcp.add_tool(tool=Tool.from_function(fn=self.search_code))
        _ = mcp.add_tool(tool=Tool.from_function(fn=self.get_file_types_for_search))

    async def _get_file(self, repository_entry: LocalRepository, path: str, truncate_lines: TRUNCATE_LINES = 100) -> File:
        """Helper function to get a file from a repository."""

        file_path: Path = repository_entry.validate_file_path(path)

        async with await open_file(file=file_path) as file:
            file_text: str = await file.read()

        url: AnyHttpUrl = repository_entry.generate_file_url(path)

        return File.from_text(
            # owner=repository_entry.owner,
            # repo=repository_entry.repo,
            # branch=repository_entry.branch,
            # path=path,
            url=url,
            text=file_text,
            truncate_lines=truncate_lines,
        )

    async def get_file_types_for_search(self) -> list[str]:
        """Get the list of file types that can be used in the `include_types` and `exclude_types` arguments of a
        code search or find files."""

        return list[str](get_args(tp=RIPGREP_TYPE_LIST))

    async def get_file(
        self,
        owner: OWNER,
        repo: REPO,
        path: PATH,
        truncate_lines: TRUNCATE_LINES = 100,
    ) -> File:
        """Get a file from the main branch of a repository."""
        repository_entry: LocalRepository = await self._prepare_repository(owner, repo)

        return await repository_entry.get_file(path=path, truncate_lines=truncate_lines)

    async def get_files(
        self,
        owner: OWNER,
        repo: REPO,
        paths: list[PATH],
        truncate_lines: TRUNCATE_LINES = 100,
    ) -> list[File]:
        """Get multiple files from the main branch of a repository (up to 20 files)."""
        repository_entry: LocalRepository = await self._prepare_repository(owner, repo)

        if len(paths) > GET_FILES_LIMIT:
            msg = f"Cannot get more than {GET_FILES_LIMIT} files from a repository."
            raise ValueError(msg)

        return [await repository_entry.get_file(path=path, truncate_lines=truncate_lines) for path in paths]

    async def find_files(
        self,
        owner: OWNER,
        repo: REPO,
        include_globs: INCLUDE_GLOBS | None = None,
        exclude_globs: EXCLUDE_GLOBS | None = None,
        include_types: INCLUDE_TYPES | None = None,
        exclude_types: EXCLUDE_TYPES | None = None,
        max_results: MAX_RESULTS = 100,
    ) -> list[BasicFileInfo]:
        """Find files (names/paths, not contents!) in the repository."""

        repository_entry: LocalRepository = await self._prepare_repository(owner=owner, repo=repo)

        included_globs_list, excluded_globs_list, included_type_list, excluded_type_list = prepare_ripgrep_arguments(
            included_globs=include_globs, excluded_globs=exclude_globs, included_types=include_types, excluded_types=exclude_types
        )

        ripgrep = (
            repository_entry.find_file_builder.include_types(ripgrep_types=included_type_list)
            .exclude_types(ripgrep_types=excluded_type_list)
            .include_globs(included_globs_list)
            .exclude_globs(excluded_globs_list)
        )

        results: list[BasicFileInfo] = []

        async for matched_path in ripgrep.arun():
            file_entry: BasicFileInfo = BasicFileInfo(path=str(matched_path))

            results.append(file_entry)

            if len(results) >= max_results:
                break

        return results

    async def search_code(
        self,
        owner: OWNER,
        repo: REPO,
        patterns: PATTERNS,
        include_globs: INCLUDE_GLOBS | None = None,
        exclude_globs: EXCLUDE_GLOBS | None = None,
        include_types: INCLUDE_TYPES | None = None,
        exclude_types: EXCLUDE_TYPES | None = None,
        max_results: MAX_RESULTS = 30,
    ) -> list[FileWithMatches]:
        """Search the code in the default branch of the repository.

        Up to 3 matches per file will be returned, Search is not case-sensitive, and up to 4 lines of context will
        be returned before and after the match. Globs are similar to the globs used with `grep` on the command line.

        For example, `python` will search for Python files, and `java` will search for Java files.
        If not provided, common types are excluded by default (binary files, lock files, etc).
        """
        repository_entry: LocalRepository = await self._prepare_repository(owner=owner, repo=repo)

        included_globs_list, excluded_globs_list, included_type_list, excluded_type_list = prepare_ripgrep_arguments(
            included_globs=include_globs, excluded_globs=exclude_globs, included_types=include_types, excluded_types=exclude_types
        )

        ripgrep: RipGrepSearch = (
            repository_entry.search_builder.auto_hybrid_regex()
            .include_globs(globs=included_globs_list)
            .exclude_globs(globs=excluded_globs_list)
            .include_types(ripgrep_types=included_type_list)
            .exclude_types(ripgrep_types=excluded_type_list)
            .before_context(context=4)
            .after_context(context=4)
            .add_patterns(patterns)
            .max_count(count=3)  # Matches per File
            .case_sensitive(case_sensitive=False)
        )

        results: list[FileWithMatches] = []

        async for result in ripgrep.arun():
            url: AnyHttpUrl = repository_entry.generate_file_url(path=str(result.path))

            file_entry_matches: list[FileEntryMatch] = search_result_to_file_entry_matches(
                search_result=result, before_context=4, after_context=4
            )

            file_with_matches: FileWithMatches = FileWithMatches(
                # owner=owner,
                # repo=repo,
                # branch=repository_entry.branch,
                # path=str(result.path),
                url=url,
                matches=file_entry_matches,
            )

            results.append(file_with_matches)

            if len(results) >= max_results:
                break

        return results

    def _clone_repository(self, owner: str, repo: str, directory: Path) -> str:
        try:
            repository: Repo = Repo.clone_from(
                f"https://github.com/{owner}/{repo}.git",
                directory,
                depth=1,
                single_branch=True,
                multi_options=["--filter=blob:limit=5000000"],
            )
        except Exception as e:
            msg = f"Error preparing repository {owner}/{repo}: {e}"
            raise RepositoryServerError(msg) from e

        return repository.active_branch.name

    async def _prepare_repository(self, owner: str, repo: str) -> LocalRepository:
        if repository := self._get_repository(owner=owner, repo=repo):
            return repository

        async with self.repository_lock:
            if repository := self._get_repository(owner=owner, repo=repo):
                return repository

            repo_directory: Path = Path(await mkdtemp(prefix=f"{owner}_{repo}", dir=str(self.clone_dir)))

            self.logger.info(f"Cloning repository {owner}/{repo} to {repo_directory}")

            branch: str = await asyncio.to_thread(self._clone_repository, owner=owner, repo=repo, directory=repo_directory)

            self.logger.info(f"Cloned repository {owner}/{repo} to {repo_directory}")

            return self._add_repository(owner=owner, repo=repo, branch=branch, local_path=repo_directory)
