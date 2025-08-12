# Uvify

[![PyPI version](https://img.shields.io/pypi/v/uvify.svg)](https://pypi.org/project/uvify/)

Turn python repositories to `uv` environments and oneliners, without diving into the code.<br>

- Generates oneliners for quick python environment setup
- Helps with migration to `uv` for faster builds in CI/CD
- It works on existing projects based on: `requirements.txt`, `pyproject.toml` or `setup.py`, recursively.
  - Supports local directories.
  - Supports GitHub links using <a href="https://gitingest.com/">Git Ingest</a>.
- It's fast!

## Prerequisites
| <a href="https://github.com/astral-sh/uv?tab=readme-ov-file#installation">uv</a>

## Demo
https://huggingface.co/spaces/avilum/uvify

[![Star History Chart](https://api.star-history.com/svg?repos=avilum/uvify&type=Date)](https://www.star-history.com/#avilum/uvify&Date)

> uv is by far the fastest python and package manager. 
<img src="assets/image.png">

<i>Source: https://github.com/astral-sh/uv</i>

You can run uvify with uv. <br>
Let's generate oneliners for a virtual environment that has `requests` installed, using PyPi or from source:
```shell
# Run on a local directory
uvx uvify . | jq

# Run on requests
uvx uvify https://github.com/psf/requests | jq
# or:
# uvx uvify psf/requests | jq

[
  ...
  {
    "file": "setup.py",
    "fileType": "setup.py",
    "oneLiner": "uv run --python '>=3.8.10' --with 'certifi>=2017.4.17,charset_normalizer>=2,<4,idna>=2.5,<4,urllib3>=1.21.1,<3,requests' python -c 'import requests; print(requests)'",
    "uvInstallFromSource": "uv run --with 'git+https://github.com/psf/requests' --python '>=3.8.10' python",
    "dependencies": [
      "certifi>=2017.4.17",
      "charset_normalizer>=2,<4",
      "idna>=2.5,<4",
      "urllib3>=1.21.1,<3"
    ],
    "packageName": "requests",
    "pythonVersion": ">=3.8",
    "isLocal": false
  }
]
```

### Parse all python artifacts in repository:
```
uvify psf/requests
uvify https://github.com/psf/requests
```

### Parse specific fields in the response
```
uvify psf/black | jq '.[] | {file: .file, pythonVersion: .pythonVersion, dependencies: .dependencies, packageName: .packageName}'
```

### Use existing python repos with 'uv':
```
uvify psf/requests | jq '.[0].oneLiner'
"uv run --with 'git+https://github.com/psf/requests' --python '3.11' python"
```
### Install a repository with 'uv' from github sources:
```
uvify psf/requests | jq '.[0].dependencies'
```

### List the dependencies.
```
uvify psf/requests | jq '.[].dependencies'
[
  "certifi>=2017.4.17",
  "charset_normalizer>=2,<4",
  "idna>=2.5,<4",
  "urllib3>=1.21.1,<3"
]
```

## Filtering Options

Uvify supports filtering which files to analyze using include and exclude patterns with glob syntax.

### Exclude directories from analysis

Skip test directories and any paths matching the pattern:
```bash
uvify --exclude "tests/*" --exclude "test_*" my-project/
```

### Include only specific directories

Analyze only files in the `src/` directory:
```bash
uvify --include "src/*" my-project/
```

Analyze only a specific subdirectory:
```bash
uvify --include "src/my_app/*" my-project/
```

### Combine include and exclude patterns

Include everything in `src/` but exclude test files:
```bash
uvify --include "src/*" --exclude "*/test_*" --exclude "*/tests/*" my-project/
```

### GitHub repositories with filtering

The filtering also works with GitHub repositories:
```bash
# Exclude test directories from a GitHub repo
uvify --exclude "tests/*" psf/requests

# Only analyze specific subdirectories  
uvify --include "src/*" --include "lib/*" myorg/myrepo
```

### Pattern Examples

- `tests/*` - Excludes any directory named "tests" and all its contents
- `test_*` - Excludes any file or directory starting with "test_"  
- `*/tests/*` - Excludes "tests" directories at any depth
- `src/my_app/*` - Includes only files within the "src/my_app/" directory
- `*.py` - Includes only Python files

**Note:** By default, uvify scans all directories for `requirements.txt`, `pyproject.toml`, and `setup.py` files. The include/exclude patterns filter which of these files to analyze based on their path.

## Uvify HTTP Server: Using uvify with client/server architecture instead of SDK

First, install uvify with the optional API dependencies:
```shell
uv add uvify[api]
# or with pip:
# pip install uvify[api]
```

Then run the server:
```shell
# Run the server using the built-in serve command
uvify serve --host 0.0.0.0 --port 8000

# Or using uvicorn directly
uv run uvicorn src.uvify:api --host 0.0.0.0 --port 8000

# Using curl
curl http://0.0.0.0:8000/psf/requests | jq

# Using wget
wget -O-  http://0.0.0.0:8000/psf/requests | jq
```


## Developing
```shell
# Install dependencies (including optional API dependencies)
uv venv
uv sync --dev --extra api
uv run pytest

# Run linter before PR 
./lint.sh

# Install editable version locally
uv run pip install --editable .
uv run python -m src.uvify --help
uv run python -m src.uvify psf/requests

# Run the HTTP API with reload
uv run uvicorn src.uvify:api --host 0.0.0.0 --port 8000 --reload 
# Or use the built-in serve command:
# uv run python -m src.uvify serve --host 0.0.0.0 --port 8000

curl http://0.0.0.0:8000/psf/requests | jq
```

# Special Thanks 
Thanks to the UV team and Astral for this amazing tool.
