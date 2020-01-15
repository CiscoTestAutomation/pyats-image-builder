#!/bin/bash
set -e

echo "[Entrypoint] Starting pyATS Docker Image ..."
echo "[Entrypoint] Workspace Directory: ${WORKSPACE}"

# activate workspace
# ------------------
echo "[Entrypoint] Activating Python virtual environment"
source ${VENV_LOC}/bin/activate

# set cwd
# -------
cd ${WORKSPACE}

# Run job or given command
# ------------------------
if [ -z "$@" ]; then
    # Nothing passed -> run bash
    [ -t 0 ] && bash
elif [ "info" = "$1" ]; then
    cat ${INSTALL_LOC}/build.yaml
else
    # Other command passed -> execute
    eval "$@"
fi
