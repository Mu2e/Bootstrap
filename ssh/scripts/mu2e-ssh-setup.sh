#!/usr/bin/env bash
#
# mu2e-ssh-setup.sh -- POSIX wrapper around mu2e-ssh-setup.py
#
# Finds a usable Python 3 and hands off every argument unchanged, so this is a
# drop-in for calling the .py directly:
#
#     scripts/mu2e-ssh-setup.sh --interactive
#     scripts/mu2e-ssh-setup.sh --fnal-user jdoe --install
#
# Works from any directory; the templates are located relative to this script.
# Set MU2E_SSH_PYTHON to force a particular interpreter.

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/mu2e-ssh-setup.py"

if [ ! -f "${SCRIPT}" ]; then
    echo "mu2e-ssh-setup.sh: cannot find ${SCRIPT}" >&2
    exit 1
fi

find_python() {
    if [ -n "${MU2E_SSH_PYTHON:-}" ]; then
        echo "${MU2E_SSH_PYTHON}"
        return 0
    fi
    for candidate in python3 python3.12 python3.11 python3.10 python3.9 python; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            # Reject a "python" that is really Python 2.
            if "${candidate}" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)' 2>/dev/null; then
                echo "${candidate}"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON="$(find_python)" || {
    cat >&2 <<'EOF'
mu2e-ssh-setup.sh: no Python 3.9 or newer found on PATH.

  Alma Linux 9 / RHEL 9 :  sudo dnf install python3
  macOS                 :  xcode-select --install   (or install from python.org)

Or point MU2E_SSH_PYTHON at an interpreter:

  MU2E_SSH_PYTHON=/opt/python3.11/bin/python3 ./mu2e-ssh-setup.sh --interactive
EOF
    exit 1
}

exec "${PYTHON}" "${SCRIPT}" "$@"
