#!/bin/bash
set -e

echo "[Entrypoint] Starting pyATS Docker Image ..."
echo "[Entrypoint] Workspace Directory: ${WORKSPACE}"

# activate workspace
# ------------------
echo "[Entrypoint] Activating Python virtual environment"
source ${VIRTUAL_ENV}/bin/activate

# set cwd
# -------
cd ${WORKSPACE}

# Run job or given command
# ------------------------
if [ -z "$1" ]; then
    # Nothing passed -> run bash
    bash
else
    # Other command passed -> execute
    exec "$@"
fi
