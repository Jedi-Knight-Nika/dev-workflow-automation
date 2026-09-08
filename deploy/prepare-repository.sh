#!/bin/sh
set -eu

# Dependencies were fetched at image build time. Native and validation containers
# never install packages from the network; a changed lockfile requires a new image.
if [ -f /workspace/frontend/package-lock.json ]; then
  if ! cmp -s /workspace/frontend/package-lock.json /opt/frontend/package-lock.json; then
    echo 'Frontend dependency lock changed; rebuild the repository runner image.' >&2
    exit 1
  fi
  mkdir -p /workspace/frontend/node_modules
  cp -a /opt/frontend/node_modules/. /workspace/frontend/node_modules/
fi
exec "$@"
