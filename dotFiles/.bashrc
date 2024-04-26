# Example .bashrc file for use by Mu2e accounts at Fermilab
#     See: https://mu2ewiki.fnal.gov/wiki/Shells#Setup_scripts
#
# This file will be sourced at the start of all shells that are interactive
# but not login shells.  We recommend that you source it in .bash_profile
# so that it is also effective for login shells.
#
# Alias to create the Mu2e working environment in a shell.
alias setup-mu2e="source /cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh"

case "$-" in
*i*)	# These commands executed for interactive shells
        set -o noclobber            #prevent overwrite when redirecting output
  	set -o ignoreeof            #prevent accidental logouts
        ;;
*)	# These commands executed for non-interactive shells
        ;;
esac

#
# system configuration - required to get jobsub and other Fermi supplied
#
if [ -f "/etc/bashrc" ]; then
    source "/etc/bashrc"
fi
#
# If you wish to add your own configuration we recommend you do so in
# .my_bashrc so that there is a clean separation of concerns.
#
if [ -f "${HOME}/.my_bashrc" ]; then
    source "${HOME}/.my_bashrc"
fi
