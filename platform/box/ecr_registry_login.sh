#!/usr/bin/env bash
# Lets k3s pull images from the private ECR repository: asks ECR for a password and writes it
# where k3s reads registry settings. The password lasts 12 hours, longer than any box session,
# so a service runs this before k3s at every boot (see install.sh).
#
# Usage: ecr_registry_login.sh <account>.dkr.ecr.<region>.amazonaws.com
#
# REGISTRIES_PATH sets where the file goes. The tests use it; the box uses the default.
set -euo pipefail

registry="${1:-}"
registries_path="${REGISTRIES_PATH:-/etc/rancher/k3s/registries.yaml}"

if [[ ! "${registry}" =~ ^[0-9]{12}\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com$ ]]; then
  echo "usage: ecr_registry_login.sh <account>.dkr.ecr.<region>.amazonaws.com" >&2
  exit 2
fi
region="${BASH_REMATCH[1]}"

# Only the owner can read the file, because it holds the password. The new file replaces the
# old one only once it is complete, so a failed sign-in leaves the last good file in place.
umask 077
mkdir -p "$(dirname "${registries_path}")"
password="$(aws ecr get-login-password --region "${region}")"
draft="${registries_path}.new"
cat > "${draft}" <<EOF
configs:
  "${registry}":
    auth:
      username: AWS
      password: ${password}
EOF
mv "${draft}" "${registries_path}"
echo "Wrote the ECR sign-in for ${registry} to ${registries_path}."
