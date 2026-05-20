#!/usr/bin/env bash

set -euo pipefail

# CostOps Native App
# Upload local package files to a named Snowflake stage using SnowSQL.
#
# Prerequisites:
# - snowsql is installed and authenticated
# - the stage already exists
#
# Example:
#   PACKAGE_ROOT=~/Documents/cost-ops/native_app \
#   STAGE_PATH='@COSTOPS_NATIVE_DEV.PACKAGE_SRC.COSTOPS_STAGE' \
#   ./scripts/upload_package_files_snowsql.sh

PACKAGE_ROOT="${PACKAGE_ROOT:-$PWD}"
STAGE_PATH="${STAGE_PATH:-@COSTOPS_NATIVE_DEV.PACKAGE_SRC.COSTOPS_STAGE}"

if ! command -v snowsql >/dev/null 2>&1; then
  echo "snowsql is required for this helper." >&2
  exit 1
fi

echo "Uploading CostOps Native App package files to ${STAGE_PATH}"

snowsql -q "PUT file://${PACKAGE_ROOT}/manifest.yml ${STAGE_PATH} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
snowsql -q "PUT file://${PACKAGE_ROOT}/setup_script.sql ${STAGE_PATH} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
snowsql -q "PUT file://${PACKAGE_ROOT}/readme.md ${STAGE_PATH} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
snowsql -q "PUT file://${PACKAGE_ROOT}/streamlit/streamlit_app.py ${STAGE_PATH}/streamlit AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
snowsql -q "PUT file://${PACKAGE_ROOT}/streamlit/environment.yml ${STAGE_PATH}/streamlit AUTO_COMPRESS=FALSE OVERWRITE=TRUE"

echo "Upload complete."
echo "Recommended next step: run native_app/sql/02_add_version_and_release_directive.sql"
