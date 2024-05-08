# Bootstrap
Repository of login scripts, editor initialization scripts and gdb configuration scripts for a
user's linux account that implements default Mu2e standards.

## Login scripts

Files:
1. dotfiles/.bash_profile
1. dotfiles/.bashrc

For a discussion of these files, see
[https://mu2ewiki.fnal.gov/wiki/Shells](https://mu2ewiki.fnal.gov/wiki/Shells).

## Editor initialization scripts

Files:
1. dotfiles/.emacs
1. dotfiles/.vimrc

For a discussion about what the recommended configurations do, see
[https://mu2ewiki.fnal.gov/wiki/Editors](https://mu2ewiki.fnal.gov/wiki/Editors).

Use of the editor initialization files in this package is optional.  These files provide an
example of how to configure your editor so that your code will meet Mu2e standards, but there alternative
settings to some fields (such as the number of spaces to interpret a tab) that still meet Mu2e standards.
These files must be copied into a users home directory, at which point they will take effect on the next invocation
of the editor.  Users are free to edit their private copies of these files, but the default values in the
repo should not be changed without first discussing with the Computing Coordinators.

## gdb initialization scripts

Files:
1. dotfiles/.gdbinit
1. dotfiles/.gdb_stl

For a discussion of debugging with gdb, see
[https://mu2ewiki.fnal.gov/wiki/CodeDebugging#gdb](https://mu2ewiki.fnal.gov/wiki/CodeDebugging#gdb).
