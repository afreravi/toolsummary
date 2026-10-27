#!/bin/bash
# Runs before the entrypoint. Builds a venv with paramiko, since the sandbox
# image does not ship it and pip install at runtime was the cause of an
# earlier failed run.
set -euo pipefail

python3 -m venv .venv
.venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt
.venv/bin/python -c "import paramiko; print('paramiko', paramiko.__version__)"
