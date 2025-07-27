#!/bin/bash

uv run --with=ruff ruff check . --fix && uv run --with=black black .