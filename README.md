# Bootstrap
Repository of login scripts, editor initialization scripts, gdb configuration scripts and ssh
configuration for a user's account that implements default Mu2e standards.

The login, editor and gdb files are for a linux account.  The ssh configuration also supports
macOS and Windows 11.

## Login scripts

Files:
1. dotFiles/.bash_profile
1. dotFiles/.bashrc

For a discussion of these files, see
[https://mu2ewiki.fnal.gov/wiki/Shells](https://mu2ewiki.fnal.gov/wiki/Shells).

## Editor initialization scripts

Files:
1. dotFiles/.emacs
1. dotFiles/.vimrc

For a discussion about what the recommended configurations do, see
[https://mu2ewiki.fnal.gov/wiki/Editors](https://mu2ewiki.fnal.gov/wiki/Editors).

Use of the editor initialization files in this package is optional.  These files provide an
example of how to configure your editor so that your code will meet Mu2e standards, but there alternative
settings to some fields (such as the number of spaces to interpret a tab) that still meet Mu2e standards.
These files must be copied into a users home directory, at which point they will take effect on the next invocation
of the editor.  Users are free to edit their private copies of these files, but the default values in the
repo should not be changed without first discussing with the Computing Coordinators.

## ssh configuration

Files:
1. ssh/scripts/mu2e-ssh-setup.py
1. ssh/templates/*.template
1. ssh/SSH-HOWTO.md

Templates and a generator that build an ssh client configuration for the Mu2e machines,
teaching ssh about the gateways, the MC-2 and MC-1 nodes, the IERC test stands, the offline
GPVMs and the git servers.  Once installed, `ssh mu2edaq09` connects through the correct
gateway, as the correct user, with the correct key.

Unlike the other files in this repository, these are not copied into your home directory by
hand.  Run the generator and it fills in your account names and key paths:

```bash
ssh/scripts/mu2e-ssh-setup.sh --interactive --dry-run   # see what it would do
ssh/scripts/mu2e-ssh-setup.sh --interactive --install   # write it to ~/.ssh
```

Use `mu2e-ssh-setup.cmd` or `mu2e-ssh-setup.ps1` on Windows.  The generator needs Python 3.9
or newer and no third-party modules.  It never overwrites an existing ssh configuration: it
backs up anything already in place, and `--dry-run` writes nothing at all.

The templates themselves contain no usernames or key paths, so please keep it that way when
editing them.

See [ssh/SSH-HOWTO.md](ssh/SSH-HOWTO.md) for the full instructions, including the per-platform
notes and troubleshooting, or `man ssh/man/man1/mu2e-ssh-setup.1` for the option reference.

## gdb initialization scripts

Files:
1. dotFiles/.gdbinit
1. dotFiles/.gdb_stl

For a discussion of debugging with gdb, see
[https://mu2ewiki.fnal.gov/wiki/CodeDebugging#gdb](https://mu2ewiki.fnal.gov/wiki/CodeDebugging#gdb).
