# Example .bashrc file for use by Mu2e accounts at Fermilab
#
# This file will be sourced at the start of all shells that are interactive
# but not login shells (unless you source it in your .bash_profile).
#
case "$-" in
*i*)	# These commands executed for interactive shells
        set -o noclobber            #prevent overwrite when redirecting output
  	set -o ignoreeof            #prevent accidental logouts
        ;;
*)	# These commands executed for non-interactive shells
        ;;
esac

if [ -f "${HOME}/.my_bashrc" ]; then
    source "${HOME}/.my_bashrc"
fi
