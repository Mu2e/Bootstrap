# .bash_profile file for use by Mu2e accounts at Fermilab
#
# This file will be sourced at the start of all login shells.
#
# Intialize a the common UPS repository (common to all experiments)
#
upsfile="/cvmfs/fermilab.opensciencegrid.org/products/common/etc/setups.sh"
if [  -r "${upsfile}" ]; then
    . "${upsfile}"
fi
unset upsfile
#
# User configuration for login shells:
#
if [ -f "${HOME}/.my_bash_profile" ]; then
    source "${HOME}/.my_bash_profile"
fi
#
# User configuration for non-login shells.
#
if [ -f "${HOME}/.bashrc" ]; then
    source "${HOME}/.bashrc"
    export BASH_ENV="${HOME}/.bashrc"
fi
