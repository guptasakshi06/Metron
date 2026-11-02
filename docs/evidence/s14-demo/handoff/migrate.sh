#!/bin/sh
set -eu
if [ "$#" -ne 3 ]; then
  echo "Usage: sh migrate.sh SOURCE NEW_WORKSPACE NEW_RESULT.json" >&2
  exit 2
fi
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec data-optimizer reproduce "$bundle_dir/bundle.json" --mode migration \
  --source "$1" --root "$2" --output "$3"
