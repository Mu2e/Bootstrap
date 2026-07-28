# Mu2e DAQ ssh Configuration HOWTO

This directory holds templates and a generator that build a working ssh client
configuration for the Mu2e DAQ machines. Running the generator gives you a
`~/.ssh/config` that knows about the gateways, the MC-2 and MC-1 nodes, the IERC
test stands, and the git servers, so that

```
ssh mu2edaq09
```

connects through the right gateway as the right user with the right key, instead
of you having to remember the hop.

The templates in `templates/` contain no personal information. The generator
fills in your username and key paths.

- [Quick start](#quick-start)
- [What gets generated](#what-gets-generated)
- [Include vs monolithic layout](#include-vs-monolithic-layout)
- [Platform notes](#platform-notes)
- [Setting up your keys first](#setting-up-your-keys-first)
- [Safety: your existing config](#safety-your-existing-config)
- [Configuration reference](#configuration-reference)
- [Host groups](#host-groups)
- [Verifying it works](#verifying-it-works)
- [Troubleshooting](#troubleshooting)
- [Customizing without losing your changes](#customizing-without-losing-your-changes)

---

## Quick start

You need Python 3.9 or newer and an ssh key. Nothing else — the generator uses
only the standard library.

From this directory:

**macOS / Linux**

```bash
./scripts/mu2e-ssh-setup.sh --interactive --dry-run    # answer the questions, see the result
./scripts/mu2e-ssh-setup.sh --interactive --install    # do it for real
```

**Windows 11**

```
scripts\mu2e-ssh-setup.cmd --interactive --dry-run
scripts\mu2e-ssh-setup.cmd --interactive --install
```

The two-step pattern is deliberate: `--dry-run` prints exactly what would be
written and touches nothing, so you can look before you leap.

Non-interactive, if you already know what you want:

```bash
./scripts/mu2e-ssh-setup.sh \
    --fnal-user jdoe \
    --key-default ~/.ssh/keys/default/id_ed25519 \
    --key-github  ~/.ssh/keys/github/id_ed25519 \
    --install
```

### The three modes

The generator has three ways to leave its output, and the default is the
cautious one.

| Invocation | What happens |
|---|---|
| `--dry-run` | Prints the plan. Writes nothing, anywhere. |
| *(neither flag)* | Writes to `./mu2e-ssh-config/` for you to inspect. Your real `~/.ssh` is untouched. |
| `--install` | Writes into `~/.ssh`, backing up anything already there. |

So `--install` is the only invocation that can change your live configuration,
and even then it backs up first. See
[Safety: your existing config](#safety-your-existing-config).

Useful additions to `--dry-run`:

```bash
./scripts/mu2e-ssh-setup.sh --fnal-user jdoe --dry-run --diff     # unified diff vs what you have now
./scripts/mu2e-ssh-setup.sh --fnal-user jdoe --dry-run --print    # print the full generated files
```

---

## What gets generated

In the default **include** layout:

```
~/.ssh/
├── config                    main file: global defaults + Include lines
├── config_mu2edaq            DAQ machines, gateways, test stands
├── config_mu2e_controlroom   MC-1 control room (only if you enable it)
├── config_mu2egpvm           Mu2e offline GPVMs (Kerberos)
├── config_novagpvm           NOvA offline GPVMs (only if you enable it)
├── config_dunegpvm           DUNE offline GPVMs (only if you enable it)
├── config_github             GitHub and Fermilab GitLab
├── config_other              YOUR entries — never overwritten
└── backup-<timestamp>/       whatever was there before
```

In **monolithic** layout you get a single `~/.ssh/config` with all of the above
concatenated in the correct order.

Every generated file is written with mode `0600` and Unix line endings, which is
what OpenSSH expects even on Windows.

### Ordering matters, and it is not what most people expect

ssh uses the **first** value it finds for any given keyword — not the last, and
not the most specific. A `Host *` block at the top of your config would win over
a `Host mu2edaq09` block further down, which is the opposite of how most
config formats behave.

That is why the generated file puts the specific host groups **before** the
generic `Host *` defaults. If you edit the file by hand, preserve that order.

---

## Include vs monolithic layout

```bash
--layout include      # separate files, pulled in with Include (default)
--layout monolithic   # one self-contained file
```

**include** is easier to live with. Each host group is its own file, so you can
regenerate one without disturbing the others, and your personal entries live in
`config_other` where nothing will overwrite them. It needs OpenSSH 7.3 or newer
(released 2016), which covers macOS, Alma 9, and the OpenSSH client built into
Windows 10 and 11.

**monolithic** produces one file that works with every client, including ones
that never learned the `Include` keyword:

- PuTTY and its relatives (they do not read `~/.ssh/config` at all, but some
  wrappers convert it)
- older Git-for-Windows bundles
- various GUI SFTP clients that parse `~/.ssh/config` themselves
- any tool that reads the config with its own parser rather than calling ssh

Because Windows users are the most likely to hit one of those, the generator
defaults to monolithic on Windows and include everywhere else. Override with
`--layout` whenever you like.

You can switch later by re-running with the other `--layout`; the generator will
back up the previous set.

---

## Platform notes

### macOS

Works out of the box. `UseKeychain yes` is included so that a passphrase you
have unlocked once is remembered by the system keychain, and `AddKeysToAgent
yes` loads the key on first use.

`UseKeychain` is an Apple extension. The generated file guards it with
`IgnoreUnknown UseKeychain`, so if you copy the file to Linux or Windows it is
ignored rather than causing an error.

### Linux (Alma Linux 9)

Works out of the box; Alma 9 ships OpenSSH 8.7.

If you use Kerberos, keep the `gssapi` feature on (it is on by default) and
`kinit` before connecting:

```bash
kinit jdoe@FNAL.GOV
ssh mu2edaq09
```

If SELinux is enforcing and ssh complains it cannot read your keys, the usual
cause is a home directory restored from a backup with the wrong labels:

```bash
restorecon -R -v ~/.ssh
```

### Windows 11

Windows 11 includes an OpenSSH client. Check with:

```
ssh -V
```

If that fails, install it from **Settings → System → Optional features → Add an
optional feature → OpenSSH Client**.

Three Windows-specific things to know:

1. **Your ssh directory is `C:\Users\<you>\.ssh`.** The generator finds this
   automatically. In the generated file the paths are written with forward
   slashes, which OpenSSH on Windows accepts and prefers, since a backslash is
   an escape character in some contexts.

2. **Paths with spaces get quoted.** `C:/Users/Jane Doe/.ssh/id_ed25519` is
   written in quotes, because ssh would otherwise split the argument at the
   space.

3. **File permissions.** Windows has no `chmod`, and OpenSSH on Windows checks
   ACLs instead. If ssh refuses your key with a permissions complaint, reset the
   ACL so only you can read it:

   ```powershell
   icacls "$env:USERPROFILE\.ssh\id_ed25519" /inheritance:r /grant:r "$env:USERNAME:R"
   ```

If PowerShell refuses to run `scripts/mu2e-ssh-setup.ps1` because of the execution
policy, either use `scripts/mu2e-ssh-setup.cmd`, which needs no policy change, or allow
local scripts for your account:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## Setting up your keys first

The generator **verifies that every key file it references actually exists**,
and refuses to write anything if one is missing. Create your keys first.

```bash
mkdir -p ~/.ssh/keys/default ~/.ssh/keys/github
chmod 700 ~/.ssh ~/.ssh/keys

ssh-keygen -t ed25519 -f ~/.ssh/keys/default/id_ed25519 -C "jdoe@mu2e"
ssh-keygen -t ed25519 -f ~/.ssh/keys/github/id_ed25519  -C "jdoe@github"
```

On Windows, in PowerShell:

```powershell
mkdir "$env:USERPROFILE\.ssh\keys\default" -Force
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\keys\default\id_ed25519" -C "jdoe@mu2e"
```

Use `ed25519` unless you are talking to something ancient that needs RSA.

Then install the public halves:

- **Fermilab machines** — append `~/.ssh/keys/default/id_ed25519.pub` to
  `~/.ssh/authorized_keys` on the target, or use `ssh-copy-id`.
- **GitHub** — paste `~/.ssh/keys/github/id_ed25519.pub` into
  <https://github.com/settings/keys>.

> **Point the generator at the private key, not the `.pub` file.**
> This is the single most common mistake. `--key-default ~/.ssh/id_ed25519.pub`
> is wrong; drop the `.pub`. The generator detects this and warns you, but it is
> easier to get right the first time.

The generator also warns if a key is group- or world-readable, since ssh will
refuse to use such a key:

```bash
chmod 600 ~/.ssh/keys/default/id_ed25519
```

To generate the config before the keys exist — for instance when preparing a
machine you have not logged into yet — use `--no-verify-keys`.

---

## Safety: your existing config

The generator will not silently clobber an ssh setup you already have.

**It never overwrites in place.** Any existing file that would change is copied
to `~/.ssh/backup-<timestamp>/` first.

**It warns and lists what it found.** Before writing anything it prints each
existing file with its size and modification time.

**It gives you a way out.**

- Interactively, it asks for confirmation and defaults to declining.
- In `--batch` mode it **aborts with exit status 2** and changes nothing unless
  you pass `--force`. A script that forgets `--force` fails safely rather than
  destroying a config.

**`config_other` is yours.** It is created only if absent and never overwritten,
so your personal host entries survive any number of regenerations.

**Re-running is a no-op.** If the generated content matches what is already
there, the generator says `already up to date` instead of manufacturing a
spurious backup. The timestamp in the header comment is ignored for this
comparison.

To restore a backup:

```bash
cp ~/.ssh/backup-20260728-143022/config ~/.ssh/config
```

`--no-backup` skips the backup entirely. It exists for scripted rebuilds of
throwaway machines; do not use it on a machine you care about.

### Exit status

| Status | Meaning |
|---|---|
| 0 | Success, or a dry run that completed |
| 1 | Bad arguments, missing templates, or ssh rejected the result |
| 2 | Aborted on purpose: existing files, or a missing key |
| 130 | Interrupted with Ctrl-C |

---

## Configuration reference

Settings come from four places. Later sources win:

```
built-in defaults  <  --config-file  <  MU2E_SSH_* environment  <  command line
```

So a shared YAML file can set the site defaults, a `MU2E_SSH_FNAL_USER` in your
shell profile can personalize it, and a command-line flag can override both for
one run.

### Command-line options

Run `mu2e-ssh-setup --help` for the authoritative list.

**Mode**

| Option | Meaning |
|---|---|
| `-i`, `--interactive` | Ask for each setting. Default when given no identifying options. |
| `--batch` | Never prompt. Fail if something required is missing. |
| `-n`, `--dry-run` | Show what would be written; change nothing. |
| `--install` | Write into the live ssh directory instead of staging. |
| `--diff` | With `--dry-run`, show a unified diff against your current files. |
| `--print` | With `--dry-run`, print the generated files in full. |

**Accounts**

| Option | Default |
|---|---|
| `--fnal-user NAME` | *required* |
| `--github-user NAME` | same as `--fnal-user` |
| `--daq-account NAME` | `mu2edaq` |
| `--shift-account NAME` | `mu2eshift` |
| `--dcs-account NAME` | `mu2edcs` |

**Keys**

| Option | Default |
|---|---|
| `--key-default PATH` | autodetected from `~/.ssh/keys/default` or `~/.ssh` |
| `--key-github PATH` | same as `--key-default` |
| `--key-fnal PATH` | same as `--key-default` |
| `--no-verify-keys` | off — keys are verified by default |

**Layout and paths**

| Option | Default |
|---|---|
| `--layout {include,monolithic}` | `include`, or `monolithic` on Windows |
| `--groups LIST` | `mu2edaq,mu2egpvm,github` |
| `--all-groups` | — |
| `--gateway-precedence {daq,shift}` | `daq` |
| `--user-config-first` | off |
| `--ssh-dir DIR` | `~/.ssh` |
| `--output-dir DIR` | `./mu2e-ssh-config`, or the ssh dir with `--install` |
| `--backup-dir DIR` | `<ssh-dir>/backup-<timestamp>` |
| `--no-backup`, `--force` | off |
| `--templates-dir DIR` | `templates/` beside the script |
| `-c`, `--config-file FILE` | — |

**Host settings**

| Option | Default |
|---|---|
| `--mc2-gateway HOST` | `mu2egateway01.fnal.gov` |
| `--ierc-gateway HOST` | `mu2edaq-gateway.fnal.gov` |
| `--kerberos-realm REALM` | `FNAL.GOV` |
| `--canonical-domain DOMAIN` | `fnal.gov` |
| `--strict-host-key-checking {yes,no,ask,accept-new}` | `accept-new` |

**Features** — each has a `--no-` counterpart, e.g. `--no-x11`.

| Feature | Default | Effect |
|---|---|---|
| `--keychain` | on (macOS only) | store passphrases in the macOS keychain |
| `--gssapi` | on | Kerberos/GSSAPI to fnal.gov hosts |
| `--x11` | on | X11 forwarding, needed for otsdaq GUIs |
| `--agent` | on | forward the ssh agent to remote hosts |
| `--canonicalize` | on | let `mu2edaq09` mean `mu2edaq09.fnal.gov` |
| `--controlmaster` | off | reuse one TCP connection for repeat logins |

**Validation**

| Option | Meaning |
|---|---|
| `--no-validate` | Skip running `ssh -G` against the result |
| `--no-color` | Plain output, for logs and dumb terminals |

### Config file

See `examples/mu2e-ssh-setup.yaml` for a fully commented template.

```yaml
fnal_user: jdoe
key_default: ~/.ssh/keys/default/id_ed25519
key_github: ~/.ssh/keys/github/id_ed25519
layout: include
groups: [mu2edaq, mu2egpvm, github]
features:
  x11: true
  controlmaster: false
```

PyYAML is used if it is installed. If it is not, a small built-in parser handles
the flat `key: value`, inline `key: [a, b]`, and one-level-nested `features:`
forms shown above — so a bare Alma 9 or Windows Python works without installing
anything.

### Environment variables

Any setting can be given as `MU2E_SSH_` plus the uppercase name:

```bash
export MU2E_SSH_FNAL_USER=jdoe
export MU2E_SSH_KEY_DEFAULT=~/.ssh/keys/default/id_ed25519
export MU2E_SSH_LAYOUT=monolithic
```

---

## Host groups

Choose with `--groups a,b,c` or `--all-groups`.

### `mu2edaq` (on by default)

DAQ-account access to the Mu2e machines:

| Pattern | Account | Reached via |
|---|---|---|
| `mu2egateway*` | `mu2edaq` | direct |
| `mu2edaq-gateway*` | `mu2edaq` | direct |
| `mu2edaq04,07,09,10,11,13,14,22` | `mu2edaq` | IERC gateway |
| `mu2e-mgr-01` | `mu2edaq` | MC-2 gateway |
| `mu2e-trk*`, `mu2e-calo*`, `mu2e-dl-*`, `mu2e-cfo*` | `mu2edaq` | MC-2 gateway |
| `mu2e-dcs-*` | `mu2edcs` | MC-2 gateway |
| `mu2e-mc1-cr-*` | `mu2eshift` | MC-2 gateway |

### `controlroom` (off by default)

Shifter access to MC-1. Only the gateways and the control room nodes, all as
`mu2eshift`.

> **The two groups overlap.** Both claim `Host mu2egateway*`, one as `mu2edaq`
> and one as `mu2eshift`. Since ssh takes the first match, enabling both means
> one account wins for the gateways. The generator warns you and lets you choose
> with `--gateway-precedence daq|shift`.
>
> Most people want just one of these groups. Take `mu2edaq` if you are a DAQ
> expert, `controlroom` if you only take shifts.

### `mu2egpvm` (on by default), `novagpvm`, `dunegpvm` (off by default)

The general purpose VMs used for offline analysis, code building and grid job
submission:

| Group | Hosts | Account |
|---|---|---|
| `mu2egpvm` | `mu2egpvm01` – `mu2egpvm07` | your Fermilab username |
| `novagpvm` | `novagpvm01` – `novagpvm12` | your Fermilab username |
| `dunegpvm` | `dunegpvm01` – `dunegpvm16` | your Fermilab username |

Unlike the DAQ machines, you log in to these as **yourself**, not a shared
account, and there is no gateway hop — they are reachable directly.

**These machines require Kerberos.** No ssh key will get you in. Get a ticket
first:

```bash
kinit yourname@FNAL.GOV
ssh mu2egpvm01
```

If ssh prompts you for a password, your ticket is missing or has expired. Check
with `klist`; a ticket typically lasts about 26 hours.

Because Kerberos is the only option on these hosts, their blocks request GSSAPI
unconditionally — even if you build the config with `--no-gssapi`. The generator
warns you if you do that, since the rest of your config would then have Kerberos
off while these hosts still need it.

Two details worth knowing:

- **The agent is deliberately not forwarded to gpvms**, even when the global
  `--agent` feature is on. These are shared multi-user machines, and a forwarded
  agent socket is usable by anyone who can read it — including root — for as
  long as you stay logged in. The delegated Kerberos credential already covers
  onward hops to dCache, jobsub and other Fermilab hosts, so you lose nothing in
  normal use. If you specifically need agent forwarding on a gpvm (say, to push
  to GitHub from there), override it in `config_other` and regenerate with
  `--user-config-first`.

- **The patterns are wildcards** (`mu2egpvm*`), not enumerated host lists, so
  nodes added to the pool later work without regenerating. This is not merely a
  convenience: ssh `Host` patterns support only `*`, `?` and `!` — there are no
  character ranges, so `mu2egpvm0[1-7]` would silently match nothing at all.

### `github` (on by default)

`github.com` and `hepcloud-git.fnal.gov`, each pinned to a specific key with
`IdentitiesOnly yes`, so that ssh offers the keys named in the config rather
than walking through every key loaded in your agent.

Be aware that the `IdentityFile` in the `Host *` block is *appended* to the
per-host one rather than replacing it — that is how ssh treats `IdentityFile`,
uniquely among its keywords. So for `github.com` ssh will offer the GitHub key
first and the default key second. The first one wins, so this works; it only
matters if you are counting authentication attempts against a server with a low
`MaxAuthTries`. Verify what will actually be offered with:

```bash
ssh -G github.com | grep identityfile
```

Note also that `github.com` uses `User git` regardless of your GitHub account
name — your identity comes from the key, not the username.

---

## Verifying it works

Ask ssh what it resolved, without connecting to anything:

```bash
ssh -G mu2edaq09.fnal.gov | grep -E '^(user|hostname|proxyjump|identityfile)'
```

Expected:

```
user mu2edaq
hostname mu2edaq09.fnal.gov
identityfile /home/jdoe/.ssh/keys/default/id_ed25519
proxyjump mu2edaq@mu2edaq-gateway.fnal.gov
```

Then actually connect:

```bash
ssh mu2edaq09.fnal.gov
ssh -T git@github.com          # expect "Hi <you>! You've successfully authenticated"
```

To watch the whole negotiation when something is wrong:

```bash
ssh -vvv mu2edaq09.fnal.gov 2>&1 | head -60
```

The generator runs `ssh -G` on its own output before declaring success, so a
syntax error is caught at generation time rather than the next time you try to
log in.

---

## Troubleshooting

### "Bad configuration option"

Your ssh is older than a keyword in the file. Check the version with `ssh -V`;
you want 7.3 or newer. The message names the offending line.

If it names `UseKeychain`, you are on a non-macOS system with a config generated
for macOS. Regenerate with `--no-keychain`.

### Include lines are ignored

The client is older than OpenSSH 7.3, or is not OpenSSH at all. Regenerate with
`--layout monolithic`.

### "Permissions 0644 for ... are too open"

```bash
chmod 600 ~/.ssh/keys/default/id_ed25519
chmod 700 ~/.ssh
```

On Windows use the `icacls` command in [Platform notes](#platform-notes).

### It asks for a password instead of using my key

Check what ssh actually offers:

```bash
ssh -v mu2edaq09.fnal.gov 2>&1 | grep -i 'offering\|identity file'
```

Common causes, roughly in order of likelihood:

- the public key is not in `authorized_keys` on the target
- the key path in the config is wrong, or points at the `.pub` file
- key permissions are too open (see above)
- your account is not authorized on that machine yet

### ProxyJump fails but the gateway works directly

Your key must be usable *from* the gateway *to* the target. Either forward your
agent (on by default) and load the key locally:

```bash
ssh-add ~/.ssh/keys/default/id_ed25519
ssh-add -l                                # confirm it is loaded
```

or put the key on the gateway.

### Kerberos/GSSAPI errors on Alma 9

```bash
kinit jdoe@FNAL.GOV
klist                                     # confirm you have a ticket
```

If you do not use Kerberos at all, `--no-gssapi` removes the attempt.

### Bare hostnames do not resolve

`ssh mu2edaq09` relies on the `canonicalize` feature. Confirm it is on:

```bash
ssh -G mu2edaq09 | grep -i canonical
```

Some VPN and split-DNS setups interact badly with hostname canonicalization. If
so, regenerate with `--no-canonicalize` and type the fully qualified names.

### I want to undo everything

```bash
ls -d ~/.ssh/backup-*                     # find the most recent
cp ~/.ssh/backup-20260728-143022/* ~/.ssh/
```

---

## Customizing without losing your changes

The generated files carry a "do not edit by hand" banner, and for good reason:
the next run overwrites them.

**Put your own entries in `~/.ssh/config_other`.** The generator creates it once
and never touches it again.

```
Host mylaptop
        HostName 192.168.1.20
        User jdoe
        ForwardX11 no
```

Because `config_other` is included *last* by default, and ssh honours the first
value it finds, a setting there cannot override one made by an earlier Mu2e
group. If you need it to win, regenerate with `--user-config-first`, which moves
the include to the top.

**To change the Mu2e defaults themselves**, edit the files in `templates/` and
re-run the generator with `--templates-dir`. If the change is one every Mu2e
user should get, send a pull request against the `Bootstrap` repository instead
of keeping it local.

---

## For maintainers: the templates

`templates/*.template` are the source of truth. They use a tiny directive
syntax:

| Syntax | Meaning |
|---|---|
| `#@ text` | comment; stripped from the output |
| `#@if feature` / `#@else` / `#@endif` | conditional block |
| `#@include-block` | replaced by the host-group includes or inlined bodies |
| `@@TOKEN@@` | substituted from the resolved settings |

Every `#@` line is stripped, so template documentation never reaches the user's
config. An unknown `@@TOKEN@@` is a hard error rather than being silently left
in place, which keeps a typo from shipping a broken config.

To add a host group: write `templates/config_<name>.template`, then add a
`Group(...)` entry to `GROUPS` in `scripts/mu2e-ssh-setup.py`. Order in that list is the
order in the generated config, which — see above — determines who wins.
