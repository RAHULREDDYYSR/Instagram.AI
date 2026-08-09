---
name: uv-python-rule
trigger: always_on
description: Ensures agents use uv for all python operations.
---

# UV Python Project Guidelines

This project uses `uv` for Python package and environment management.

## Guidelines

1. **Running Scripts**: Do not use `python script.py`. Always use `uv run script.py`.
2. **Adding Dependencies**: Do not use `pip install`. Always use `uv add <package>` to add dependencies to the `pyproject.toml`.
3. **Environment**: Do not create or activate standard `venv` environments manually. `uv run` handles the environment automatically based on the `pyproject.toml`.
