import typer
from typing_extensions import Annotated
import json
from gitingest import ingest


from collections import OrderedDict
import tempfile
import os
import re
import sys
import urllib.parse
import toml
from pathlib import Path as PathLib
import ast

# Optional FastAPI imports
try:
    from fastapi import FastAPI, Path, HTTPException

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Create dummy classes to avoid NameError
    FastAPI = None
    Path = None
    HTTPException = None

# ==================== CONSTANTS ====================

# File patterns and extensions
RELEVANT_FILES = ("requirements.txt", "pyproject.toml", "setup.py")
REQUIREMENTS_FILE = "requirements.txt"
PYPROJECT_FILE = "pyproject.toml"
SETUP_PY_FILE = "setup.py"

# GitHub configuration
GITHUB_BASE_URL = "https://github.com/"
GITHUB_GIT_PREFIX = "git+https://github.com/"

# Version specifiers regex pattern
VERSION_SPECIFIERS_PATTERN = r"==|>=|<=|!=|~=|>|<|==="

# Requirements.txt parsing
REQUIREMENTS_COMMENT_CHAR = "#"
ENV_MARKER_SEPARATOR = ";"

# TOML configuration keys
TOML_TOOL_KEY = "tool"
TOML_POETRY_KEY = "poetry"
TOML_PROJECT_KEY = "project"
TOML_BUILD_SYSTEM_KEY = "build-system"
TOML_DEPENDENCIES_KEY = "dependencies"
TOML_REQUIRES_KEY = "requires"
TOML_PYTHON_KEY = "python"
TOML_NAME_KEY = "name"

# Python version patterns
PYTHON_VERSION_PATTERN = r'python\s*=\s*"([^"]+)"'
PYTHON_REQUIRES_PATTERN = r'python_requires\s*=\s*["\']([^"\']+)["\']'
PYTHON_DEPENDENCY_PATTERN = r"^python([<>=!~].*)?$"

# Setup.py configuration
SETUP_FUNCTION_NAME = "setup"
SETUP_INSTALL_REQUIRES = "install_requires"
SETUP_PYTHON_REQUIRES = "python_requires"
SETUP_NAME_ATTR = "name"
SETUP_PACKAGES_ATTR = "packages"

# Setup.py regex patterns
SETUP_INSTALL_REQUIRES_PATTERN = r"install_requires\s*=\s*\[(.*?)\]"
SETUP_NAME_PATTERN = r'name\s*=\s*["\']([^"\']+)["\']'
SETUP_PACKAGES_PATTERN = r"packages\s*=\s*\[(.*?)\]"
SETUP_STRING_LITERAL_PATTERN = r'"([^"]+)"|\'([^\']+)\''
PYPROJECT_NAME_PATTERN = r'^name\s*=\s*["\']([^"\']+)["\']'

# Content parsing markers
FILE_MARKER = "FILE:"
SEPARATOR_MARKER = "="
SYMLINK_MARKER = "SYMLINK:"

# Command templates
UV_RUN_BASE_TEMPLATE = "uv run --python '{python_version}'"
UV_RUN_WITH_DEPS_TEMPLATE = (
    "uv run --python '{python_version}' --with '{dependencies}' python"
)
UV_RUN_WITH_PACKAGE_TEMPLATE = "uv run --python '{python_version}' --with '{dependencies}' python -c 'import {import_name}; print({import_name})'"
UV_RUN_IMPORT_PACKAGE_TEMPLATE = "uv run --python '{python_version}' python -c 'import {package_name}; print({package_name})'"
UV_RUN_PLAIN_TEMPLATE = "uv run --python '{python_version}' python"
UV_INSTALL_FROM_GIT_TEMPLATE = (
    "uv run --with 'git+https://github.com/{source}' --python '{python_version}' python"
)

# Default values
DEFAULT_PYTHON_MAJOR = sys.version_info.major
DEFAULT_PYTHON_MINOR = sys.version_info.minor
DEFAULT_PYTHON_VERSION = f"{DEFAULT_PYTHON_MAJOR}.{DEFAULT_PYTHON_MINOR}"

# Error messages
ERROR_DIR_NOT_EXISTS = "Directory does not exist: {path}"
ERROR_NOT_A_DIRECTORY = "Path is not a directory: {path}"
ERROR_INVALID_GITHUB_REPO = "Invalid GitHub repository format"

# API configuration
API_DEFAULT_PAGE_SIZE = 100
API_DEFAULT_PAGE = 1

# File processing
MIN_PATH_COMPONENTS = 1
PATH_SEPARATOR = "/"

# ==================== END CONSTANTS ====================

# Create CLI and FastAPI app
cli = typer.Typer()

# Create FastAPI app only if FastAPI is available
if FASTAPI_AVAILABLE:
    api = FastAPI()
else:
    api = None

# Helper to extract dependencies from requirements.txt


def parse_requirements_txt(content: str) -> list[str]:
    deps = []
    # print(f"Parsing requirements.txt content:\n{content}")
    for line in content.splitlines():
        line = line.strip()
        # print(f"Processing line: '{line}'")
        if not line or line.startswith(REQUIREMENTS_COMMENT_CHAR):
            # print(f"Skipping line (empty or comment): '{line}'")
            continue
        # Preserve lines with environment markers
        if ENV_MARKER_SEPARATOR in line:
            # print(f"Adding line with environment marker: '{line}'")
            deps.append(line)
            continue
        # Remove version specifiers for other lines
        # Split on any of these version specifiers: ==, >=, <=, !=, ~=, >, <, ===
        dep = re.split(VERSION_SPECIFIERS_PATTERN, line)[0].strip()
        if dep:
            # print(f"Adding dependency: '{dep}' (from line: '{line}')")
            deps.append(dep)
    # print(f"Final dependencies list: {deps}")
    return deps


# Helper to extract dependencies from pyproject.toml


def parse_pyproject_toml(content: str) -> list[str]:
    deps = []
    # Try to parse as TOML for robust extraction
    try:
        data = toml.loads(content)

        # Handle poetry dependencies
        if (
            TOML_TOOL_KEY in data
            and TOML_POETRY_KEY in data[TOML_TOOL_KEY]
            and TOML_DEPENDENCIES_KEY in data[TOML_TOOL_KEY][TOML_POETRY_KEY]
        ):
            poetry_deps = data[TOML_TOOL_KEY][TOML_POETRY_KEY][TOML_DEPENDENCIES_KEY]
            deps.extend(
                [
                    dep
                    for dep in poetry_deps.keys()
                    if dep != TOML_PYTHON_KEY  # Skip python version requirement
                ]
            )

        # PEP 621: [project] dependencies
        if TOML_PROJECT_KEY in data and TOML_DEPENDENCIES_KEY in data[TOML_PROJECT_KEY]:
            project_deps = data[TOML_PROJECT_KEY][TOML_DEPENDENCIES_KEY]
            # Handle both list and dict formats
            if isinstance(project_deps, list):
                deps.extend(
                    [
                        re.split(VERSION_SPECIFIERS_PATTERN, dep)[0].strip()
                        for dep in project_deps
                    ]
                )
            elif isinstance(project_deps, dict):
                deps.extend(
                    [dep for dep in project_deps.keys() if dep != TOML_PYTHON_KEY]
                )

        # Handle build-system requires
        if (
            TOML_BUILD_SYSTEM_KEY in data
            and TOML_REQUIRES_KEY in data[TOML_BUILD_SYSTEM_KEY]
        ):
            build_deps = data[TOML_BUILD_SYSTEM_KEY][TOML_REQUIRES_KEY]
            deps.extend(
                [
                    re.split(VERSION_SPECIFIERS_PATTERN, dep)[0].strip()
                    for dep in build_deps
                ]
            )

    except Exception:
        # print(f"Error parsing pyproject.toml: {e}")
        return []

    return list(set(deps))  # Remove duplicates


# Helper to extract dependencies from setup.py


def parse_setup_py(content: str) -> tuple[list[str], str | None]:
    """Parse setup.py for install_requires and python_requires, even if defined as variables or passed as variables."""
    deps = []
    py_version = None
    var_map = {}
    try:
        tree = ast.parse(content)
        # Track variable assignments
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # Only store lists/tuples of strings
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            values = []
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Str):
                                    values.append(elt.s)
                                elif isinstance(elt, ast.Constant) and isinstance(
                                    elt.value, str
                                ):
                                    values.append(elt.value)
                            var_map[target.id] = values
                        # Also store string assignments (for python_requires)
                        elif isinstance(node.value, ast.Str):
                            var_map[target.id] = node.value.s
                        elif isinstance(node.value, ast.Constant) and isinstance(
                            node.value.value, str
                        ):
                            var_map[target.id] = node.value.value
        # Find setup() call
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and hasattr(node.func, "id")
                and node.func.id == SETUP_FUNCTION_NAME
            ):
                for kw in node.keywords:
                    if kw.arg == SETUP_INSTALL_REQUIRES:
                        # Direct list/tuple
                        if isinstance(kw.value, (ast.List, ast.Tuple)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Str):
                                    deps.append(elt.s)
                                elif isinstance(elt, ast.Constant) and isinstance(
                                    elt.value, str
                                ):
                                    deps.append(elt.value)
                        # Variable reference
                        elif isinstance(kw.value, ast.Name):
                            var_name = kw.value.id
                            if var_name in var_map and isinstance(
                                var_map[var_name], list
                            ):
                                deps.extend(var_map[var_name])
                    if kw.arg == SETUP_PYTHON_REQUIRES:
                        if isinstance(kw.value, ast.Str):
                            py_version = kw.value.s
                        elif isinstance(kw.value, ast.Constant) and isinstance(
                            kw.value.value, str
                        ):
                            py_version = kw.value.value
                        elif isinstance(kw.value, ast.Name):
                            var_name = kw.value.id
                            if var_name in var_map and isinstance(
                                var_map[var_name], str
                            ):
                                py_version = var_map[var_name]
    except Exception:
        # fallback: regex
        match = re.search(SETUP_INSTALL_REQUIRES_PATTERN, content, re.DOTALL)
        if match:
            items = match.group(1)
            for dep in re.findall(SETUP_STRING_LITERAL_PATTERN, items):
                dep_name = dep[0] or dep[1]
                if dep_name:
                    deps.append(dep_name)
        match_py = re.search(PYTHON_REQUIRES_PATTERN, content)
        if match_py:
            py_version = match_py.group(1)
    return deps, py_version


def extract_package_name_from_setup_py(content: str) -> str:
    # First, try to find name="<package_name>"
    name_match = re.search(SETUP_NAME_PATTERN, content)
    if name_match:
        return name_match.group(1)

    # If name is not a literal, fall back to packages=['<package_name>']
    # Find packages=[...]
    packages_match = re.search(SETUP_PACKAGES_PATTERN, content, re.DOTALL)
    if packages_match:
        # Extract the first string literal from the list
        package_list_str = packages_match.group(1)
        first_package_match = re.search(SETUP_STRING_LITERAL_PATTERN, package_list_str)
        if first_package_match:
            return first_package_match.group(1)

    return None


def extract_package_name_from_pyproject_toml(content: str) -> str:
    match = re.search(PYPROJECT_NAME_PATTERN, content, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def detect_project_source(source: str) -> tuple[str, bool]:
    """Detect if the source is a GitHub repo or a local directory.
    Returns (normalized_source, is_github)
    """
    # GitHub URL
    if source.startswith(GITHUB_BASE_URL):
        parsed = urllib.parse.urlparse(source)
        path = parsed.path.strip(PATH_SEPARATOR)
        if path.count(PATH_SEPARATOR) >= MIN_PATH_COMPONENTS:
            owner_repo = PATH_SEPARATOR.join(path.split(PATH_SEPARATOR)[:2])
            return owner_repo, True
    # owner/repo format
    if PATH_SEPARATOR in source and not source.startswith(PATH_SEPARATOR):
        owner_repo = PATH_SEPARATOR.join(source.split(PATH_SEPARATOR)[:2])
        return owner_repo, True
    # Otherwise, treat as local directory
    return source, False


def extract_project_files_multi(source: str, is_github: bool) -> list[dict]:
    """Extract all relevant files and their parsed info from a repo or local dir.

    [
        {
            "file": "pyproject.toml",
            "fileType": "pyproject.toml",
            "oneLiner": "uv run --python '>=3.10' --with 'gitingest,rich,toml,typer,uvify' python -c 'impor
    t uvify; print(uvify)'",
            "uvInstallFromSource": null,
            "dependencies": [
                "gitingest",
                "rich",
                "toml",
                "typer"
            ],
            "packageName": "uvify",
            "pythonVersion": ">=3.10",
            "isLocal": true
        },
        ...
    ]
    """
    found_files = []
    files_content = {}
    if is_github:
        repo_url = f"{GITHUB_BASE_URL}{source}"
        with tempfile.TemporaryDirectory() as _:
            if ingest:
                # print(f"Ingesting from {repo_url}")
                summary, tree, content = ingest(
                    repo_url,
                    include_patterns=set(RELEVANT_FILES),
                )
                # print(f"Content type: {type(content)}")
                # print(f"Content preview:\n{content[:500]}")

                if isinstance(content, str):
                    content_dict = OrderedDict()

                    # First, find all FILE: markers and their content
                    current_file = None
                    current_content = []

                    for line in content.splitlines():
                        if line.startswith(FILE_MARKER):
                            # If we were collecting content for a previous file, save it
                            if current_file and current_content:
                                file_content = "\n".join(current_content).strip()
                                if any(
                                    current_file.endswith(fname)
                                    for fname in RELEVANT_FILES
                                ):
                                    # print(f"Saving content for {current_file}")
                                    content_dict[current_file] = file_content

                            # Start new file
                            current_file = line.replace(FILE_MARKER, "").strip()
                            current_content = []
                            # print(f"Found file: {current_file}")
                        elif line.startswith(SEPARATOR_MARKER):
                            # Skip separator lines
                            continue
                        elif line.startswith(SYMLINK_MARKER):
                            # Skip symlink blocks
                            current_file = None
                            current_content = []
                        elif current_file:
                            # Collect content lines for current file
                            current_content.append(line)

                    # Don't forget to save the last file
                    if current_file and current_content:
                        file_content = "\n".join(current_content).strip()
                        if any(
                            current_file.endswith(fname) for fname in RELEVANT_FILES
                        ):
                            # print(f"Saving content for {current_file}")
                            content_dict[current_file] = file_content

                    # print(f"\nFound {len(content_dict)} relevant files: {list(content_dict.keys())}")
                    files_content = content_dict
                else:
                    # Handle case where content is already a dict
                    # print("Content is a dict, processing directly")
                    for k, v in content.items():
                        if any(k.endswith(fname) for fname in RELEVANT_FILES):
                            # print(f"Found relevant file in dict: {k}")
                            files_content[k] = v
    else:
        dir_path = PathLib(source).resolve()
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(ERROR_DIR_NOT_EXISTS.format(path=dir_path))
        for root, _, files in os.walk(dir_path):
            for fname in files:
                if fname in RELEVANT_FILES:
                    file_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(file_path, dir_path)
                    with open(file_path, "r") as f:
                        files_content[rel_path] = f.read()

    # parse each file
    for rel_path, file_content in files_content.items():
        # print(f"\nProcessing file: {rel_path}")
        # print(f"Content preview: {file_content[:100]}")
        file_type = None
        dependencies = []
        py_version = None
        package_name = None
        if rel_path.endswith(REQUIREMENTS_FILE):
            file_type = REQUIREMENTS_FILE
            dependencies = parse_requirements_txt(file_content)
            # print(f"Found dependencies in requirements.txt: {dependencies}")
        elif rel_path.endswith(PYPROJECT_FILE):
            file_type = PYPROJECT_FILE
            dependencies = parse_pyproject_toml(file_content)
            m = re.search(PYTHON_VERSION_PATTERN, file_content)
            if m:
                py_version = m.group(1)
            package_name = extract_package_name_from_pyproject_toml(file_content)
            # print(f"Found dependencies in pyproject.toml: {dependencies}")
        elif rel_path.endswith(SETUP_PY_FILE):
            file_type = SETUP_PY_FILE
            dependencies, py_version = parse_setup_py(file_content)
            package_name = extract_package_name_from_setup_py(file_content)
            # print(f"Found dependencies in setup.py: {dependencies}")

        # Remove python version specifiers from dependencies
        dep_list = sorted(
            set(d for d in dependencies if not re.match(PYTHON_DEPENDENCY_PATTERN, d))
        )
        # print(f"Final dependency list: {dep_list}")

        default_python_version = py_version or DEFAULT_PYTHON_VERSION
        if package_name:
            import_name = package_name.replace("-", "_")
        else:
            import_name = None

        # compose the command
        if dep_list:
            if package_name:
                one_liner = UV_RUN_WITH_PACKAGE_TEMPLATE.format(
                    python_version=default_python_version,
                    dependencies=",".join(dep_list + [package_name]),
                    package_name=package_name,
                    import_name=import_name,
                )
            else:
                one_liner = UV_RUN_WITH_DEPS_TEMPLATE.format(
                    python_version=default_python_version,
                    dependencies=",".join(dep_list),
                )
        else:
            if package_name:
                one_liner = UV_RUN_IMPORT_PACKAGE_TEMPLATE.format(
                    python_version=default_python_version,
                    package_name=package_name,
                    import_name=import_name,
                )
            else:
                one_liner = UV_RUN_PLAIN_TEMPLATE.format(
                    python_version=default_python_version
                )

        uv_install_from_git_command = None
        if is_github:
            uv_install_from_git_command = UV_INSTALL_FROM_GIT_TEMPLATE.format(
                source=source, python_version=default_python_version
            )

        found_files.append(
            {
                "file": rel_path,
                "fileType": file_type,
                "oneLiner": one_liner,
                "uvInstallFromSource": uv_install_from_git_command,
                "dependencies": dep_list,
                "packageName": package_name,
                "pythonVersion": default_python_version,
                "isLocal": not is_github,
            }
        )
    return found_files


def _analyze_repo_logic(source: str) -> list[dict]:
    normalized_source, is_github = detect_project_source(source)
    return extract_project_files_multi(normalized_source, is_github)


@cli.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    repo_name: Annotated[
        str,
        typer.Argument(
            help="GitHub repository (owner/repo or URL) or path to local directory"
        ),
    ] = None,
):
    """Analyze a GitHub repository or local directory to generate uv commands."""
    if ctx.invoked_subcommand is None:
        if repo_name is None:
            print("Error: Repository name is required", file=sys.stderr)
            raise typer.Exit(1)
        try:
            result = _analyze_repo_logic(repo_name)
            print(json.dumps(result, indent=4))
            return result
        except ValueError as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            sys.exit(1)


@cli.command()
def serve(
    host: Annotated[str, typer.Option(help="Host to bind to")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to bind to")] = 8000,
):
    """Start the FastAPI server for the uvify API."""
    if not FASTAPI_AVAILABLE:
        print(
            "Error: FastAPI is not installed. Install it with 'pip install uvify[api]' or 'uv add uvify[api]'",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import uvicorn

        uvicorn.run(api, host=host, port=port)
    except ImportError:
        print(
            "Error: uvicorn is not installed. Install it with 'pip install uvify[api]' or 'uv add uvify[api]'",
            file=sys.stderr,
        )
        sys.exit(1)


# FastAPI route - only define if FastAPI is available
if FASTAPI_AVAILABLE:

    @api.get("/{repo_name:path}")
    def analyze_repo_api(
        repo_name: str = Path(
            ...,
            description="GitHub repository (owner/repo or URL) or path to local directory",
        ),
    ):
        try:
            return _analyze_repo_logic(repo_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    cli()
