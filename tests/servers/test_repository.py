import tempfile
from logging import getLogger
from pathlib import Path

import pytest
from inline_snapshot import snapshot
from pydantic import AnyHttpUrl

from github_code_search.servers.repository import FileEntryMatch, FileLines, FileWithMatches, RepositoryServer

logger = getLogger(__name__)


def test_init():
    repository_server: RepositoryServer = RepositoryServer(logger=logger, clone_dir=Path("temp"))
    assert repository_server is not None


@pytest.fixture
async def repository_server():
    with tempfile.TemporaryDirectory() as temp_dir:
        repository_server: RepositoryServer = RepositoryServer(logger=logger, clone_dir=Path(temp_dir))
        yield repository_server


async def test_simple_search(repository_server: RepositoryServer):
    search_result: list[FileWithMatches] = await repository_server.search_code(
        owner="strawgate", repo="github-issues-e2e-test", patterns=["world!"], max_results=1
    )

    assert search_result == snapshot(
        [
            FileWithMatches(
                url=AnyHttpUrl("https://github.com/strawgate/github-issues-e2e-test/blob/main/README.md"),
                matches=[
                    FileEntryMatch(
                        before=FileLines(
                            root={47: "```python", 48: "from gith_ub import ExistentialCoder", 50: "coder = ExistentialCoder()"}
                        ),
                        match=FileLines(root={51: "coder.analyze_code(\"def hello_world(): print('Hello, World!')\")"}),
                        after=FileLines(
                            root={
                                52: "# Output: \"But what is 'Hello'? What is 'World'? Are we not all just strings in the cosmic interpreter?\"",
                                53: "```",
                                55: "## Philosophy",
                            }
                        ),
                    ),
                    FileEntryMatch(
                        before=FileLines(
                            root={
                                70: "MIT License - because even in the digital realm, we must respect the cosmic copyright of existence.",
                                72: "---",
                            }
                        ),
                        match=FileLines(
                            root={
                                74: "*\"In the beginning was the Word, and the Word was `console.log('Hello, World!')`\"* - The Gospel of G.I.T.H.U.B."
                            }
                        ),
                    ),
                ],
            )
        ]
    )


async def test_simple_search_function_name(repository_server: RepositoryServer):
    search_result: list[FileWithMatches] = await repository_server.search_code(
        owner="strawgate", repo="github-issues-e2e-test", patterns=["hello_world"], max_results=1
    )

    assert search_result == snapshot(
        [
            FileWithMatches(
                url=AnyHttpUrl("https://github.com/strawgate/github-issues-e2e-test/blob/main/README.md"),
                matches=[
                    FileEntryMatch(
                        before=FileLines(
                            root={47: "```python", 48: "from gith_ub import ExistentialCoder", 50: "coder = ExistentialCoder()"}
                        ),
                        match=FileLines(root={51: "coder.analyze_code(\"def hello_world(): print('Hello, World!')\")"}),
                        after=FileLines(
                            root={
                                52: "# Output: \"But what is 'Hello'? What is 'World'? Are we not all just strings in the cosmic interpreter?\"",
                                53: "```",
                                55: "## Philosophy",
                            }
                        ),
                    )
                ],
            )
        ]
    )


async def test_simple_search_class_name(repository_server: RepositoryServer):
    search_result: list[FileWithMatches] = await repository_server.search_code(
        owner="strawgate", repo="github-issues-e2e-test", patterns=["ExistentialCoder"], max_results=1
    )

    assert search_result == snapshot(
        [
            FileWithMatches(
                url=AnyHttpUrl("https://github.com/strawgate/github-issues-e2e-test/blob/main/src/existential_coder.py"),
                matches=[
                    FileEntryMatch(
                        before=FileLines(
                            root={26: "    contemplation_level: ContemplationLevel", 27: "    line_number: Optional[int] = None"}
                        ),
                        match=FileLines(root={30: "class ExistentialCoder:"}),
                        after=FileLines(
                            root={
                                31: '    """',
                                32: "    The main class that provides existential guidance for developers.",
                                34: "    This class analyzes code not just for syntax errors, but for deeper",
                            }
                        ),
                    )
                ],
            )
        ]
    )


async def test_simple_search_class_name_exclude_globs(repository_server: RepositoryServer):
    search_result: list[FileWithMatches] = await repository_server.search_code(
        owner="strawgate", repo="github-issues-e2e-test", patterns=["ExistentialCoder"], exclude_globs=["*.py"], max_results=1
    )

    assert search_result == snapshot(
        [
            FileWithMatches(
                url=AnyHttpUrl("https://github.com/strawgate/github-issues-e2e-test/blob/main/README.md"),
                matches=[
                    FileEntryMatch(
                        before=FileLines(root={45: "## Usage", 47: "```python"}),
                        match=FileLines(root={48: "from gith_ub import ExistentialCoder"}),
                        after=FileLines(
                            root={
                                51: "coder.analyze_code(\"def hello_world(): print('Hello, World!')\")",
                                52: "# Output: \"But what is 'Hello'? What is 'World'? Are we not all just strings in the cosmic interpreter?\"",
                            }
                        ),
                    ),
                    FileEntryMatch(match=FileLines(root={50: "coder = ExistentialCoder()"}), after=FileLines(root={53: "```"})),
                ],
            )
        ]
    )


async def test_simple_search_class_name_exclude_types(repository_server: RepositoryServer):
    search_result: list[FileWithMatches] = await repository_server.search_code(
        owner="strawgate", repo="github-issues-e2e-test", patterns=["ExistentialCoder"], exclude_types=["python"], max_results=10
    )

    assert search_result == snapshot(
        [
            FileWithMatches(
                url=AnyHttpUrl("https://github.com/strawgate/github-issues-e2e-test/blob/main/README.md"),
                matches=[
                    FileEntryMatch(
                        before=FileLines(root={45: "## Usage", 47: "```python"}),
                        match=FileLines(root={48: "from gith_ub import ExistentialCoder"}),
                        after=FileLines(
                            root={
                                51: "coder.analyze_code(\"def hello_world(): print('Hello, World!')\")",
                                52: "# Output: \"But what is 'Hello'? What is 'World'? Are we not all just strings in the cosmic interpreter?\"",
                            }
                        ),
                    ),
                    FileEntryMatch(match=FileLines(root={50: "coder = ExistentialCoder()"}), after=FileLines(root={53: "```"})),
                ],
            )
        ]
    )
