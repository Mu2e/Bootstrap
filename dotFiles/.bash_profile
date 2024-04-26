# .bash_profile file for use by Mu2e accounts at Fermilab
#     See: https://mu2ewiki.fnal.gov/wiki/Shells#Setup_scripts
##
# This file will be sourced at the start of all login shells.
#
# Include configuration common to login and non-login shells.
#
if [ -f "${HOME}/.bashrc" ]; then
    source "${HOME}/.bashrc"
    export BASH_ENV="${HOME}/.bashrc"
fi
#
# If you wish to add your own configuration we recommend you do so in
# .my_bash_profile so that there is a clean separation concerns.
#
if [ -f "${HOME}/.my_bash_profile" ]; then
    source "${HOME}/.my_bash_profile"
fi
