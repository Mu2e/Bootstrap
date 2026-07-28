#!/usr/bin/env python3
"""Generate a personalized Mu2e DAQ ssh client configuration.

Reads the templates in ssh/templates/, substitutes the user's account names and
key paths, and writes either a set of Include-based files or a single monolithic
config.  Existing files are backed up, never overwritten in place.

Runs on macOS, Linux (Alma 9) and Windows 11 with a stock Python 3.9+.
No third-party dependencies are required; PyYAML is used for --config-file if it
is installed, otherwise a small built-in parser handles the flat key: value form.

See SSH-HOWTO.md for the full narrative documentation.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.0.0"
PROG = "mu2e-ssh-setup"

# Configuration precedence, lowest to highest:
#     built-in defaults < config file < environment < command line
ENV_PREFIX = "MU2E_SSH_"

# ---------------------------------------------------------------------------
# Host groups
# ---------------------------------------------------------------------------
#
# Order matters.  ssh takes the FIRST value it finds for any keyword, so the
# specific host groups must precede the generic "Host *" block, and among
# themselves the earlier group wins any overlapping pattern.


class Group:
    """One optional block of host definitions."""

    def __init__(self, name, template, filename, summary, default_on):
        self.name = name
        self.template = template
        self.filename = filename
        self.summary = summary
        self.default_on = default_on


GROUPS = [
    Group(
        "mu2edaq",
        "config_mu2edaq.template",
        "config_mu2edaq",
        "Mu2e DAQ machines: MC-2 room, IERC test stands, CFO/tracker/calo nodes",
        True,
    ),
    Group(
        "controlroom",
        "config_mu2e_controlroom.template",
        "config_mu2e_controlroom",
        "MC-1 control room shifter accounts",
        False,
    ),
    Group(
        "mu2egpvm",
        "config_mu2egpvm.template",
        "config_mu2egpvm",
        "Mu2e offline GPVM nodes, mu2egpvm01-07 (Kerberos)",
        True,
    ),
    Group(
        "novagpvm",
        "config_novagpvm.template",
        "config_novagpvm",
        "NOvA offline GPVM nodes, novagpvm01-12 (Kerberos)",
        False,
    ),
    Group(
        "dunegpvm",
        "config_dunegpvm.template",
        "config_dunegpvm",
        "DUNE offline GPVM nodes, dunegpvm01-16 (Kerberos)",
        False,
    ),
    Group(
        "github",
        "config_github.template",
        "config_github",
        "GitHub and Fermilab GitLab (hepcloud-git)",
        True,
    ),
]

# Groups that both claim "Host mu2egateway*" but map it to different accounts.
CONFLICTING_GROUPS = ("mu2edaq", "controlroom")

# Groups whose hosts accept Kerberos and nothing else. Turning the global gssapi
# feature off while one of these is enabled produces a config that cannot log in,
# so it is worth a warning.
KERBEROS_ONLY_GROUPS = ("mu2egpvm", "novagpvm", "dunegpvm")

USER_CONFIG_FILE = "config_other"
MAIN_CONFIG_FILE = "config"

# Feature flags consumed by #@if in the templates.
FEATURES = {
    "keychain": "use the macOS keychain to hold key passphrases",
    "gssapi": "enable Kerberos/GSSAPI authentication to fnal.gov hosts",
    "x11": "forward X11 (needed for otsdaq GUIs, DAQ Interface windows)",
    "agent": "forward the ssh agent through to remote hosts",
    "canonicalize": "let bare names like 'mu2edaq09' resolve to .fnal.gov",
    "controlmaster": "reuse one TCP connection for repeat logins (faster)",
}

DEFAULT_KEY_CANDIDATES = ("id_ed25519", "id_rsa", "id_ecdsa")


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

class Term:
    """Minimal colour support that degrades to plain text."""

    def __init__(self, enabled=True):
        self.enabled = enabled and self._supported()

    @staticmethod
    def _supported():
        if os.environ.get("NO_COLOR"):
            return False
        if not sys.stdout.isatty():
            return False
        if os.name == "nt":
            # Windows 10+ consoles understand ANSI once VT processing is on.
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
                return True
            except Exception:
                return False
        return os.environ.get("TERM", "dumb") != "dumb"

    def _wrap(self, code, text):
        return "\033[%sm%s\033[0m" % (code, text) if self.enabled else text

    def bold(self, t):
        return self._wrap("1", t)

    def red(self, t):
        return self._wrap("31", t)

    def green(self, t):
        return self._wrap("32", t)

    def yellow(self, t):
        return self._wrap("33", t)

    def cyan(self, t):
        return self._wrap("36", t)


TERM = Term()
_WARNINGS = []


def info(msg):
    print(msg)


def step(msg):
    print(TERM.cyan("==> ") + msg)


def ok(msg):
    print(TERM.green("  OK  ") + msg)


def warn(msg):
    _WARNINGS.append(msg)
    print(TERM.yellow("  WARN  ") + msg, file=sys.stderr)


def fail(msg, code=1):
    print(TERM.red("  ERROR  ") + msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform():
    if sys.platform == "darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    return "linux"


def platform_label(plat):
    return {"macos": "macOS", "windows": "Windows", "linux": "Linux"}.get(plat, plat)


def supports_include(plat):
    """Does this platform's ssh understand the Include keyword?

    Include arrived in OpenSSH 7.3 (2016).  macOS and Alma 9 are far past that.
    Windows is the problem case: the OpenSSH client shipped in-box with Windows
    10/11 does support Include, but PuTTY, older Git-for-Windows builds and
    various GUI clients that read ~/.ssh/config do not.  Default Windows to
    monolithic so the result works with whatever client the user actually has.
    """
    return plat != "windows"


def detect_ssh_version():
    """Return (major, minor) of the local ssh client, or None."""
    exe = shutil.which("ssh")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-V"], capture_output=True, text=True, timeout=10
        )
    except Exception:
        return None
    text = (proc.stderr or "") + (proc.stdout or "")
    match = re.search(r"OpenSSH[_ ](\d+)\.(\d+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def default_ssh_dir():
    return Path.home() / ".ssh"


def expand(path_str):
    """Expand ~ and environment variables, returning an absolute Path."""
    if path_str is None:
        return None
    text = os.path.expandvars(str(path_str).strip())
    return Path(text).expanduser()


def ssh_path(path, plat):
    """Render a filesystem path the way the ssh config file wants to see it.

    OpenSSH on Windows accepts forward slashes and is happier with them, since
    a backslash is an escape character in some contexts.  Quote anything with
    a space in it -- "C:/Users/Jane Doe/.ssh/key" must be quoted or ssh splits
    the argument at the space.
    """
    text = str(path)
    if plat == "windows":
        text = text.replace("\\", "/")
    if " " in text:
        text = '"%s"' % text
    return text


def tilde_path(path, home, plat):
    """Use ~/... form where possible; it travels better between machines."""
    try:
        rel = Path(path).relative_to(home)
    except ValueError:
        return ssh_path(path, plat)
    return ssh_path("~/" + rel.as_posix(), plat)


# ---------------------------------------------------------------------------
# Key discovery and verification
# ---------------------------------------------------------------------------

def find_default_key(ssh_dir):
    """Guess a sensible default identity file."""
    for sub in (ssh_dir / "keys" / "default", ssh_dir):
        if not sub.is_dir():
            continue
        for name in DEFAULT_KEY_CANDIDATES:
            candidate = sub / name
            if candidate.is_file():
                return candidate
    return ssh_dir / "id_ed25519"


def looks_like_public_key(path):
    try:
        with open(path, "rb") as handle:
            head = handle.read(64)
    except OSError:
        return False
    return head.startswith(b"ssh-") or head.startswith(b"ecdsa-") or head.startswith(
        b"sk-"
    )


def check_key(path, label, require=True):
    """Verify a private key exists and looks usable.

    Returns True if the key is present and plausible.  Missing keys are an
    error when require is set; permission and public/private mix-ups are
    warnings, since the user may have a good reason.
    """
    if path is None:
        return False
    if not path.exists():
        msg = "%s key not found: %s" % (label, path)
        if require:
            print(TERM.red("  ERROR  ") + msg, file=sys.stderr)
            pub = Path(str(path) + ".pub")
            if pub.exists():
                print(
                    "          (found %s -- ssh wants the PRIVATE key, without .pub)"
                    % pub,
                    file=sys.stderr,
                )
            return False
        warn(msg)
        return False

    if path.is_dir():
        print(
            TERM.red("  ERROR  ") + "%s key is a directory, not a file: %s"
            % (label, path),
            file=sys.stderr,
        )
        return False

    if path.suffix == ".pub" or looks_like_public_key(path):
        warn(
            "%s key %s looks like a PUBLIC key. ssh needs the private half "
            "(the file without the .pub suffix)." % (label, path)
        )
        return True

    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            warn(
                "%s key %s has permissions %04o; ssh will refuse to use it. "
                "Fix with: chmod 600 %s" % (label, path, mode, path)
            )
    return True


# ---------------------------------------------------------------------------
# Config file loading
# ---------------------------------------------------------------------------

def load_config_file(path):
    """Load settings from YAML.

    Uses PyYAML when available.  Falls back to a minimal parser that handles
    the flat "key: value" and "key: [a, b]" forms this script actually needs,
    so a bare Alma 9 or Windows Python can still read its own config.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("top level of %s must be a mapping" % path)
        return data
    except ImportError:
        pass

    def scalar(value):
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            return [
                item.strip().strip('"').strip("'")
                for item in inner.split(",")
                if item.strip()
            ]
        low = value.lower()
        if low in ("true", "yes", "on"):
            return True
        if low in ("false", "no", "off"):
            return False
        return value

    data = {}
    # Name of the mapping we are currently indented under, if any. Only one
    # level of nesting is supported, which is all this config shape needs.
    parent = None
    parent_indent = 0

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("- "):
            raise ValueError(
                "%s:%d: block lists are not supported without PyYAML; "
                "write it inline as 'key: [a, b]'" % (path, lineno)
            )
        if ":" not in stripped:
            raise ValueError("%s:%d: expected 'key: value'" % (path, lineno))

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if parent is not None and indent > parent_indent:
            data[parent][key] = scalar(value)
            continue

        parent = None
        if value == "":
            # A bare "key:" opens a nested mapping.
            data[key] = {}
            parent = key
            parent_indent = indent
        else:
            data[key] = scalar(value)

    return data


def env_overrides():
    """Collect MU2E_SSH_* environment variables as lowercase keys."""
    found = {}
    for key, value in os.environ.items():
        if key.startswith(ENV_PREFIX) and value != "":
            found[key[len(ENV_PREFIX):].lower()] = value
    return found


def as_bool(value, label):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    raise ValueError("%s: expected a yes/no value, got %r" % (label, value))


# ---------------------------------------------------------------------------
# Template engine
# ---------------------------------------------------------------------------

# Any line starting with "#@" belongs to the template, not the output. A known
# keyword right after the "#@" is a directive; anything else is a comment.
DIRECTIVE = re.compile(r"^\s*#@\s*([A-Za-z][\w-]*)?\s*(.*)$")
DIRECTIVE_NAMES = ("if", "else", "endif", "include-block")
TOKEN = re.compile(r"@@([A-Z0-9_]+)@@")


class TemplateError(Exception):
    pass


def render(template_text, values, features, source_name, blocks=None):
    """Expand a template.

    Directives, one per line:
        #@ <text>            comment, dropped from the output
        #@if <feature>       emit the following lines only if feature is on
        #@else
        #@endif
        #@include-block      replaced with the caller-supplied block text

    Tokens of the form @@NAME@@ are substituted from values.
    """
    out = []
    # Stack of (emitting_here, branch_already_taken, seen_else).
    stack = []

    def emitting():
        return all(frame[0] for frame in stack)

    for lineno, line in enumerate(template_text.splitlines(), 1):
        match = DIRECTIVE.match(line)
        if match:
            name, arg = match.group(1), match.group(2).strip()

            if name not in DIRECTIVE_NAMES:
                # A plain "#@ ..." documentation comment. Dropped either way.
                continue

            if name == "if":
                if not arg:
                    raise TemplateError("%s:%d: #@if needs a feature name" % (source_name, lineno))
                if arg not in features:
                    raise TemplateError(
                        "%s:%d: unknown feature %r" % (source_name, lineno, arg)
                    )
                cond = bool(features[arg])
                stack.append([emitting() and cond, cond, False])
                continue

            if name == "else":
                if not stack:
                    raise TemplateError("%s:%d: #@else without #@if" % (source_name, lineno))
                frame = stack[-1]
                if frame[2]:
                    raise TemplateError("%s:%d: duplicate #@else" % (source_name, lineno))
                frame[2] = True
                outer = all(f[0] for f in stack[:-1])
                frame[0] = outer and not frame[1]
                continue

            if name == "endif":
                if not stack:
                    raise TemplateError("%s:%d: #@endif without #@if" % (source_name, lineno))
                stack.pop()
                continue

            if name == "include-block":
                if emitting() and blocks:
                    out.append(blocks.rstrip("\n"))
                continue

        if emitting():
            out.append(line)

    if stack:
        raise TemplateError("%s: unterminated #@if" % source_name)

    text = "\n".join(out)

    missing = set()

    def replace(match):
        key = match.group(1)
        if key not in values:
            missing.add(key)
            return match.group(0)
        return str(values[key])

    text = TOKEN.sub(replace, text)
    if missing:
        raise TemplateError(
            "%s: no value for token(s): %s" % (source_name, ", ".join(sorted(missing)))
        )

    # Collapse the runs of blank lines that dropped directives leave behind.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def prompt(question, default=None, validate=None):
    suffix = " [%s]: " % default if default not in (None, "") else ": "
    while True:
        try:
            answer = input(TERM.bold(question) + suffix).strip()
        except EOFError:
            print()
            fail("stdin closed during interactive prompt; "
                 "re-run with --batch and command-line options instead")
        except KeyboardInterrupt:
            print()
            fail("aborted by user", code=130)
        if not answer and default is not None:
            answer = str(default)
        if not answer:
            print("  A value is required.")
            continue
        if validate:
            problem = validate(answer)
            if problem:
                print("  " + TERM.yellow(problem))
                continue
        return answer


def prompt_yes_no(question, default=True):
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        try:
            answer = input(TERM.bold(question) + suffix).strip().lower()
        except EOFError:
            print()
            fail("stdin closed during interactive prompt; "
                 "re-run with --batch and command-line options instead")
        except KeyboardInterrupt:
            print()
            fail("aborted by user", code=130)
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please answer y or n.")


def prompt_choice(question, choices, default):
    info("")
    info(TERM.bold(question))
    for index, (key, label) in enumerate(choices, 1):
        marker = " (default)" if key == default else ""
        info("  %d) %s%s" % (index, label, marker))
    while True:
        try:
            answer = input("Choice [%s]: " % default).strip().lower()
        except EOFError:
            print()
            fail("stdin closed during interactive prompt; "
                 "re-run with --batch and command-line options instead")
        except KeyboardInterrupt:
            print()
            fail("aborted by user", code=130)
        if not answer:
            return default
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(choices):
                return choices[index - 1][0]
        for key, _label in choices:
            if answer == key:
                return key
        print("  Please choose one of the listed options.")


def run_interactive(settings, plat, ssh_dir):
    """Walk the user through the settings, seeded with whatever we already have."""
    info("")
    info(TERM.bold("=" * 72))
    info(TERM.bold("  Mu2e DAQ ssh configuration -- interactive setup"))
    info(TERM.bold("=" * 72))
    info("")
    info("Detected platform : %s" % platform_label(plat))
    ver = detect_ssh_version()
    info("ssh client        : %s" % ("OpenSSH %d.%d" % ver if ver else "not found on PATH"))
    info("ssh directory     : %s" % ssh_dir)
    info("")
    info("Press Enter to accept the value shown in [brackets].")
    info("")

    info(TERM.bold("--- Accounts ---"))
    settings["fnal_user"] = prompt(
        "Your Fermilab (services) username", settings.get("fnal_user")
    )
    settings["daq_account"] = prompt(
        "Shared account for DAQ machines", settings.get("daq_account", "mu2edaq")
    )
    settings["shift_account"] = prompt(
        "Shared account for control room shifts", settings.get("shift_account", "mu2eshift")
    )
    settings["dcs_account"] = prompt(
        "Shared account for DCS nodes", settings.get("dcs_account", "mu2edcs")
    )

    info("")
    info(TERM.bold("--- Host groups ---"))
    info("Which sets of hosts should be configured?")
    info("")
    enabled = []
    for group in GROUPS:
        info("  %s -- %s" % (TERM.cyan(group.name), group.summary))
        if prompt_yes_no("    include this group?", group.name in settings["groups"]):
            enabled.append(group.name)
    settings["groups"] = enabled

    if all(name in enabled for name in CONFLICTING_GROUPS):
        info("")
        warn(
            "The 'mu2edaq' and 'controlroom' groups both define 'Host mu2egateway*', "
            "with different accounts (%s vs %s). ssh honours whichever comes first."
            % (settings["daq_account"], settings["shift_account"])
        )
        which = prompt_choice(
            "Which account should win for the gateway machines?",
            [
                ("daq", "%s -- I connect as DAQ expert" % settings["daq_account"]),
                ("shift", "%s -- I take control room shifts" % settings["shift_account"]),
            ],
            "daq",
        )
        settings["gateway_precedence"] = which

    if "github" in enabled:
        info("")
        info(TERM.bold("--- Git hosting ---"))
        settings["github_user"] = prompt(
            "Your GitHub username", settings.get("github_user") or settings["fnal_user"]
        )

    info("")
    info(TERM.bold("--- Key files ---"))
    info("Give the path to the PRIVATE key (the file with no .pub suffix).")
    info("")

    def key_check(answer):
        path = expand(answer)
        if not path.exists():
            pub = Path(str(path) + ".pub")
            if pub.exists():
                return ("%s does not exist, but %s does -- you probably want the "
                        "private key (drop the .pub)." % (path, pub))
            return "%s does not exist. Type it again, or 'skip' to use it anyway." % path
        return None

    def ask_key(label, current):
        while True:
            answer = prompt(label, current)
            if answer.lower() == "skip":
                return current
            path = expand(answer)
            if path.exists():
                return path
            problem = key_check(answer)
            print("  " + TERM.yellow(problem))
            if prompt_yes_no("    Use this path anyway?", False):
                return path

    settings["key_default"] = ask_key(
        "Default key (used for Mu2e DAQ hosts)", settings.get("key_default")
    )
    if "github" in enabled:
        settings["key_github"] = ask_key(
            "Key for github.com", settings.get("key_github") or settings["key_default"]
        )
        settings["key_fnal"] = ask_key(
            "Key for hepcloud-git.fnal.gov",
            settings.get("key_fnal") or settings["key_default"],
        )

    info("")
    info(TERM.bold("--- Layout ---"))
    info("The Mu2e configuration can be written two ways:")
    info("")
    info("  include     ~/.ssh/config plus one file per host group, pulled in")
    info("              with the Include keyword. Easier to update piecemeal.")
    info("              Needs OpenSSH 7.3+ (macOS, Alma 9, Windows in-box ssh).")
    info("")
    info("  monolithic  one self-contained ~/.ssh/config. Works with every")
    info("              client including PuTTY and older Git-for-Windows.")
    info("")
    default_layout = "include" if supports_include(plat) else "monolithic"
    if not supports_include(plat):
        info(TERM.yellow(
            "  On Windows the in-box OpenSSH client handles Include, but PuTTY and\n"
            "  some GUI clients do not, so 'monolithic' is the safe default here."
        ))
        info("")
    settings["layout"] = prompt_choice(
        "Which layout?",
        [("include", "include -- separate files"),
         ("monolithic", "monolithic -- one file")],
        default_layout,
    )

    info("")
    info(TERM.bold("--- Options ---"))
    for name, description in FEATURES.items():
        if name == "keychain" and plat != "macos":
            settings["features"][name] = False
            continue
        settings["features"][name] = prompt_yes_no(
            "%s (%s)?" % (name, description), settings["features"].get(name, False)
        )

    settings["strict_host_key_checking"] = prompt_choice(
        "Host key checking policy",
        [
            ("accept-new", "accept-new -- trust on first use, warn if a key changes (recommended)"),
            ("ask", "ask -- prompt for every unknown host"),
            ("no", "no -- never check (convenient, but hides man-in-the-middle attacks)"),
        ],
        settings.get("strict_host_key_checking", "accept-new"),
    )

    return settings


# ---------------------------------------------------------------------------
# Output planning and writing
# ---------------------------------------------------------------------------

# The "Generated by ... on <date>" banner changes on every run. Ignore it when
# deciding whether a file really differs, so that re-running with the same
# settings is a no-op instead of a spurious "your config would change" warning.
STAMP_LINE = re.compile(r"^#\s+Generated by .* on .*$", re.MULTILINE)


def comparable(text):
    if text is None:
        return None
    return STAMP_LINE.sub("#  Generated by mu2e-ssh-setup", text)


class Plan:
    """What we intend to write, and what already sits in the way."""

    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.files = []          # list of (path, content, kind)
        self.existing = []       # paths that already exist and differ
        self.unchanged = []      # paths whose content already matches

    def add(self, path, content, kind="generated"):
        self.files.append((Path(path), content, kind))

    def scan_existing(self):
        self.existing = []
        self.unchanged = []
        for path, content, kind in self.files:
            if kind == "preserve" or not path.exists():
                continue
            try:
                current = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                current = None
            if comparable(current) == comparable(content):
                self.unchanged.append(path)
            else:
                self.existing.append(path)
        return self.existing


def timestamp():
    return time.strftime("%Y%m%d-%H%M%S")


def backup_existing(paths, backup_dir, dry_run):
    """Move existing files aside into a timestamped directory."""
    if not paths:
        return None
    step("Backing up %d existing file(s) to %s" % (len(paths), backup_dir))
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = backup_dir / path.name
        if dry_run:
            info("  would copy  %s -> %s" % (path, target))
        else:
            shutil.copy2(str(path), str(target))
            ok("%s -> %s" % (path.name, target))
    return backup_dir


def write_files(plan, dry_run, mode=0o600):
    for path, content, kind in plan.files:
        if kind == "preserve" and path.exists():
            info("  keeping     %s (already exists, left untouched)" % path)
            continue
        if dry_run:
            info("  would write %s (%d bytes)" % (path, len(content.encode("utf-8"))))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        # Newline is forced to "\n": OpenSSH reads CRLF badly in some places,
        # notably at the end of a ProxyJump or key path.
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        if os.name != "nt":
            os.chmod(str(path), mode)
        ok("wrote %s" % path)


def secure_ssh_dir(ssh_dir, dry_run):
    if dry_run or os.name == "nt":
        return
    ssh_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(ssh_dir), 0o700)
    except OSError as exc:
        warn("could not set permissions on %s: %s" % (ssh_dir, exc))


def validate_with_ssh(config_path):
    """Ask the real ssh client to parse what we produced."""
    exe = shutil.which("ssh")
    if not exe:
        warn("ssh not found on PATH; skipping syntax validation")
        return True
    try:
        proc = subprocess.run(
            [exe, "-F", str(config_path), "-G", "mu2edaq09.fnal.gov"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        warn("could not run ssh to validate the config: %s" % exc)
        return True

    stderr = "\n".join(
        line for line in (proc.stderr or "").splitlines()
        if "Pseudo-terminal" not in line
    ).strip()

    if proc.returncode != 0:
        print(TERM.red("  ERROR  ") + "ssh rejected the generated config:", file=sys.stderr)
        for line in (stderr or "(no message)").splitlines():
            print("          " + line, file=sys.stderr)
        return False
    if stderr:
        warn("ssh parsed the config with complaints:")
        for line in stderr.splitlines():
            print("          " + line, file=sys.stderr)
    return True


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def template_search_path():
    """Where to look for templates/, in order.

    The script normally lives in ssh/scripts/ with the templates one level up in
    ssh/templates/, but it still works if someone copies it next to them.
    """
    here = Path(__file__).resolve().parent
    return [here / "templates", here.parent / "templates", Path.cwd() / "templates"]


def find_templates_dir():
    for candidate in template_search_path():
        if (candidate / "config.template").is_file():
            return candidate
    return None


def read_template(templates_dir, name):
    path = templates_dir / name
    if not path.is_file():
        fail("template not found: %s" % path)
    return path.read_text(encoding="utf-8")


def build_values(settings, plat, ssh_dir, layout):
    home = Path.home()
    mc2_gateway = settings["mc2_gateway"]
    ierc_gateway = settings["ierc_gateway"]
    return {
        "GENERATOR_VERSION": VERSION,
        "GENERATED_ON": time.strftime("%Y-%m-%d %H:%M:%S"),
        "PLATFORM": platform_label(plat),
        "LAYOUT": layout,
        "SSH_DIR": tilde_path(ssh_dir, home, plat),
        "LOCAL_USER": settings["fnal_user"],
        "FNAL_USER": settings["fnal_user"],
        "GITHUB_USER": settings.get("github_user") or settings["fnal_user"],
        "DAQ_ACCOUNT": settings["daq_account"],
        "SHIFT_ACCOUNT": settings["shift_account"],
        "DCS_ACCOUNT": settings["dcs_account"],
        "MC2_GATEWAY": mc2_gateway,
        "IERC_GATEWAY": ierc_gateway,
        "IERC_PROXYJUMP": "%s@%s" % (settings["daq_account"], ierc_gateway),
        # Built here rather than as two adjacent tokens in the template: with
        # @@..@@ delimiters, "@@FNAL_USER@@@@@REALM@@" is genuinely ambiguous.
        "KERBEROS_PRINCIPAL": "%s@%s" % (
            settings["fnal_user"], settings["kerberos_realm"]
        ),
        "KERBEROS_REALM": settings["kerberos_realm"],
        "CANONICAL_DOMAIN": settings["canonical_domain"],
        "STRICT_HOST_KEY_CHECKING": settings["strict_host_key_checking"],
        "KEY_DEFAULT": tilde_path(settings["key_default"], home, plat),
        "KEY_GITHUB": tilde_path(
            settings.get("key_github") or settings["key_default"], home, plat
        ),
        "KEY_FNAL": tilde_path(
            settings.get("key_fnal") or settings["key_default"], home, plat
        ),
    }


def ordered_groups(settings):
    """Return the enabled groups in the order they must appear in the config."""
    names = list(settings["groups"])
    selected = [g for g in GROUPS if g.name in names]
    if all(name in names for name in CONFLICTING_GROUPS):
        if settings.get("gateway_precedence", "daq") == "shift":
            selected.sort(key=lambda g: 0 if g.name == "controlroom" else 1)
    return selected


def assemble(settings, plat, out_dir, templates_dir):
    """Render every file and return a Plan."""
    layout = settings["layout"]
    ssh_dir = settings["ssh_dir"]
    features = dict(settings["features"])
    values = build_values(settings, plat, ssh_dir, layout)
    plan = Plan(out_dir)

    groups = ordered_groups(settings)

    rendered_groups = []
    for group in groups:
        text = render(
            read_template(templates_dir, group.template),
            values,
            features,
            group.template,
        )
        rendered_groups.append((group, text))

    user_first = settings.get("user_config_first", False)

    if layout == "include":
        lines = []
        include_dir = values["SSH_DIR"]
        if user_first:
            lines.append("# Your own entries come first, so they override the")
            lines.append("# Mu2e defaults below.")
            lines.append("Include %s/%s" % (include_dir, USER_CONFIG_FILE))
            lines.append("")
        for group, _text in rendered_groups:
            lines.append("Include %s/%s" % (include_dir, group.filename))
        for group in GROUPS:
            if group not in [g for g, _ in rendered_groups]:
                lines.append("# Include %s/%s   (not enabled)"
                             % (include_dir, group.filename))
        if not user_first:
            lines.append("")
            lines.append("# Your own entries. Never touched by mu2e-ssh-setup.")
            lines.append("Include %s/%s" % (include_dir, USER_CONFIG_FILE))
        blocks = "\n".join(lines)

        for group, text in rendered_groups:
            plan.add(out_dir / group.filename, text)
    else:
        chunks = []
        separator = "#" * 75
        for group, text in rendered_groups:
            chunks.append(separator)
            chunks.append("# BEGIN host group: %s" % group.name)
            chunks.append(separator)
            chunks.append(text.rstrip("\n"))
            chunks.append("")
        chunks.append(separator)
        chunks.append("# Your own entries: add them below, or keep them in")
        chunks.append("# %s/%s and re-run with --layout include."
                      % (values["SSH_DIR"], USER_CONFIG_FILE))
        chunks.append(separator)
        blocks = "\n".join(chunks)

    main_text = render(
        read_template(templates_dir, "config.template"),
        values,
        features,
        "config.template",
        blocks=blocks,
    )
    plan.add(out_dir / MAIN_CONFIG_FILE, main_text)

    if layout == "include":
        user_text = render(
            read_template(templates_dir, "config_other.template"),
            values,
            features,
            "config_other.template",
        )
        plan.add(out_dir / USER_CONFIG_FILE, user_text, kind="preserve")

    return plan


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Generate a personalized Mu2e DAQ ssh client configuration.",
        epilog="""\
examples:
  # Walk through the questions, then preview without touching anything
  %(prog)s --interactive --dry-run

  # Preview, using values from the command line
  %(prog)s --fnal-user jdoe --key-default ~/.ssh/id_ed25519 --dry-run

  # Build into a staging directory for review (the default action)
  %(prog)s --fnal-user jdoe --output-dir ./ssh-staged

  # Build and install straight into ~/.ssh, backing up whatever is there
  %(prog)s --fnal-user jdoe --install

  # Windows / PuTTY: one self-contained file
  %(prog)s --fnal-user jdoe --layout monolithic --install

settings precedence, lowest to highest:
  built-in defaults  <  --config-file  <  MU2E_SSH_* environment  <  options

Every option below can be given in the config file under the same name with
dashes replaced by underscores, or in the environment as MU2E_SSH_<NAME>.
""",
    )

    parser.add_argument("--version", action="version",
                        version="%(prog)s " + VERSION)

    mode = parser.add_argument_group("mode")
    mode.add_argument("-i", "--interactive", action="store_true",
                      help="ask for each setting (default when no options are given)")
    mode.add_argument("--batch", action="store_true",
                      help="never prompt; fail if a required value is missing")
    mode.add_argument("-n", "--dry-run", action="store_true",
                      help="show what would be written, change nothing on disk")
    mode.add_argument("--install", action="store_true",
                      help="write into the live ssh directory (default: stage in ./mu2e-ssh-config)")
    mode.add_argument("--diff", action="store_true",
                      help="with --dry-run, show a unified diff against existing files")
    mode.add_argument("--print", dest="print_only", action="store_true",
                      help="with --dry-run, print the generated files to stdout")

    accounts = parser.add_argument_group("accounts")
    accounts.add_argument("--fnal-user", metavar="NAME",
                          help="your Fermilab services username")
    accounts.add_argument("--github-user", metavar="NAME",
                          help="your GitHub username (default: same as --fnal-user)")
    accounts.add_argument("--daq-account", metavar="NAME",
                          help="shared account on the DAQ machines (default: mu2edaq)")
    accounts.add_argument("--shift-account", metavar="NAME",
                          help="shared account for control room shifts (default: mu2eshift)")
    accounts.add_argument("--dcs-account", metavar="NAME",
                          help="shared account on the DCS nodes (default: mu2edcs)")

    keys = parser.add_argument_group("key files")
    keys.add_argument("--key-default", metavar="PATH",
                      help="private key used for the Mu2e DAQ hosts")
    keys.add_argument("--key-github", metavar="PATH",
                      help="private key for github.com (default: --key-default)")
    keys.add_argument("--key-fnal", metavar="PATH",
                      help="private key for hepcloud-git.fnal.gov (default: --key-default)")
    keys.add_argument("--no-verify-keys", action="store_true",
                      help="do not check that the key files exist")

    layout = parser.add_argument_group("layout")
    layout.add_argument("--layout", choices=("include", "monolithic"),
                        help="separate Include files, or one self-contained config "
                             "(default: include, except monolithic on Windows)")
    layout.add_argument("--groups", metavar="LIST",
                        help="comma-separated host groups to enable: %s"
                             % ",".join(g.name for g in GROUPS))
    layout.add_argument("--all-groups", action="store_true",
                        help="enable every host group")
    layout.add_argument("--gateway-precedence", choices=("daq", "shift"),
                        help="which account wins for mu2egateway* when both the "
                             "mu2edaq and controlroom groups are enabled")
    layout.add_argument("--user-config-first", action="store_true",
                        help="include config_other before the Mu2e groups, so your "
                             "own settings take precedence")

    paths = parser.add_argument_group("paths")
    paths.add_argument("--ssh-dir", metavar="DIR",
                       help="ssh directory the generated files will refer to "
                            "(default: ~/.ssh)")
    paths.add_argument("--output-dir", metavar="DIR",
                       help="where to write the files (default: ./mu2e-ssh-config, "
                            "or the ssh dir with --install)")
    paths.add_argument("--backup-dir", metavar="DIR",
                       help="where to put backups (default: <ssh-dir>/backup-<timestamp>)")
    paths.add_argument("--no-backup", action="store_true",
                       help="do not back up existing files (dangerous)")
    paths.add_argument("--force", action="store_true",
                       help="do not ask before replacing existing files")
    paths.add_argument("--templates-dir", metavar="DIR",
                       help="directory holding the .template files "
                            "(default: alongside this script)")
    paths.add_argument("-c", "--config-file", metavar="FILE",
                       help="read settings from a YAML file")

    hosts = parser.add_argument_group("host settings")
    hosts.add_argument("--mc2-gateway", metavar="HOST",
                       help="gateway for the MC-2 machines "
                            "(default: mu2egateway01.fnal.gov)")
    hosts.add_argument("--ierc-gateway", metavar="HOST",
                       help="gateway for the IERC test stands "
                            "(default: mu2edaq-gateway.fnal.gov)")
    hosts.add_argument("--kerberos-realm", metavar="REALM",
                       help="Kerberos realm for the gpvm kinit examples "
                            "(default: FNAL.GOV)")
    hosts.add_argument("--canonical-domain", metavar="DOMAIN",
                       help="domain appended to bare hostnames (default: fnal.gov)")
    hosts.add_argument("--strict-host-key-checking",
                       choices=("yes", "no", "ask", "accept-new"),
                       help="StrictHostKeyChecking policy (default: accept-new)")

    features = parser.add_argument_group("features")
    for name, description in FEATURES.items():
        flag = name.replace("_", "-")
        features.add_argument("--%s" % flag, dest="feat_%s" % name,
                              action="store_true", default=None,
                              help="enable: %s" % description)
        features.add_argument("--no-%s" % flag, dest="feat_%s" % name,
                              action="store_false", default=None,
                              help=argparse.SUPPRESS)

    checks = parser.add_argument_group("validation")
    checks.add_argument("--no-validate", action="store_true",
                        help="skip running 'ssh -G' against the result")
    checks.add_argument("--no-color", action="store_true",
                        help="disable coloured output")

    return parser


def resolve_settings(args, parser):
    """Merge defaults, config file, environment and command line."""
    plat = detect_platform()

    settings = {
        "fnal_user": None,
        "github_user": None,
        "daq_account": "mu2edaq",
        "shift_account": "mu2eshift",
        "dcs_account": "mu2edcs",
        "key_default": None,
        "key_github": None,
        "key_fnal": None,
        "mc2_gateway": "mu2egateway01.fnal.gov",
        "ierc_gateway": "mu2edaq-gateway.fnal.gov",
        "kerberos_realm": "FNAL.GOV",
        "canonical_domain": "fnal.gov",
        "strict_host_key_checking": "accept-new",
        "layout": None,
        "groups": [g.name for g in GROUPS if g.default_on],
        "gateway_precedence": "daq",
        "user_config_first": False,
        "ssh_dir": None,
        "features": {
            "keychain": plat == "macos",
            "gssapi": True,
            "x11": True,
            "agent": True,
            "canonicalize": True,
            "controlmaster": False,
        },
    }

    scalar_keys = (
        "fnal_user", "github_user", "daq_account", "shift_account", "dcs_account",
        "mc2_gateway", "ierc_gateway", "kerberos_realm", "canonical_domain",
        "strict_host_key_checking", "layout", "gateway_precedence", "ssh_dir",
    )
    path_keys = ("key_default", "key_github", "key_fnal")

    def absorb(source, origin):
        for key, value in source.items():
            key = key.replace("-", "_")
            if key in ("features",):
                if not isinstance(value, dict):
                    fail("%s: 'features' must be a mapping" % origin)
                for feat, on in value.items():
                    feat = feat.replace("-", "_")
                    if feat not in FEATURES:
                        fail("%s: unknown feature %r" % (origin, feat))
                    settings["features"][feat] = as_bool(on, "%s: features.%s" % (origin, feat))
            elif key in FEATURES:
                settings["features"][key] = as_bool(value, "%s: %s" % (origin, key))
            elif key == "groups":
                if isinstance(value, str):
                    value = [item.strip() for item in value.split(",") if item.strip()]
                settings["groups"] = list(value)
            elif key == "user_config_first":
                settings[key] = as_bool(value, "%s: %s" % (origin, key))
            elif key in path_keys:
                settings[key] = expand(value)
            elif key in scalar_keys:
                settings[key] = str(value)
            else:
                warn("%s: ignoring unrecognized setting %r" % (origin, key))

    if args.config_file:
        path = expand(args.config_file)
        if not path.is_file():
            fail("config file not found: %s" % path)
        try:
            absorb(load_config_file(path), str(path))
        except (ValueError, OSError) as exc:
            fail("could not read %s: %s" % (path, exc))

    try:
        absorb(env_overrides(), "environment")
    except ValueError as exc:
        fail(str(exc))

    for key in scalar_keys:
        value = getattr(args, key, None)
        if value is not None:
            settings[key] = value
    for key in path_keys:
        value = getattr(args, key, None)
        if value is not None:
            settings[key] = expand(value)
    for name in FEATURES:
        value = getattr(args, "feat_%s" % name, None)
        if value is not None:
            settings["features"][name] = value
    if args.user_config_first:
        settings["user_config_first"] = True
    if args.all_groups:
        settings["groups"] = [g.name for g in GROUPS]
    elif args.groups:
        settings["groups"] = [g.strip() for g in args.groups.split(",") if g.strip()]

    known = {g.name for g in GROUPS}
    unknown = [g for g in settings["groups"] if g not in known]
    if unknown:
        fail("unknown host group(s): %s (choose from %s)"
             % (", ".join(unknown), ", ".join(sorted(known))))
    if not settings["groups"]:
        fail("no host groups selected; there would be nothing to generate")

    if settings["ssh_dir"]:
        settings["ssh_dir"] = expand(settings["ssh_dir"])
    else:
        settings["ssh_dir"] = default_ssh_dir()

    if settings["layout"] is None:
        settings["layout"] = "include" if supports_include(plat) else "monolithic"

    if settings["features"]["keychain"] and plat != "macos":
        warn("UseKeychain is a macOS feature; disabling it for %s" % platform_label(plat))
        settings["features"]["keychain"] = False

    return settings, plat


def show_summary(settings, plat, out_dir, install):
    info("")
    info(TERM.bold("--- Summary ---"))
    info("  platform         : %s" % platform_label(plat))
    info("  layout           : %s" % settings["layout"])
    info("  host groups      : %s" % ", ".join(g.name for g in ordered_groups(settings)))
    info("  Fermilab user    : %s" % settings["fnal_user"])
    if "github" in settings["groups"]:
        info("  GitHub user      : %s" % (settings.get("github_user") or settings["fnal_user"]))
    info("  DAQ account      : %s" % settings["daq_account"])
    info("  shift account    : %s" % settings["shift_account"])
    info("  default key      : %s" % settings["key_default"])
    if "github" in settings["groups"]:
        info("  github key       : %s" % (settings.get("key_github") or settings["key_default"]))
        info("  fnal gitlab key  : %s" % (settings.get("key_fnal") or settings["key_default"]))
    on = [n for n, v in settings["features"].items() if v]
    info("  features on      : %s" % (", ".join(sorted(on)) or "(none)"))
    info("  host key policy  : %s" % settings["strict_host_key_checking"])
    info("  output directory : %s%s" % (out_dir, "  (LIVE ssh dir)" if install else ""))
    info("")


def show_diff(plan):
    import difflib

    for path, content, kind in plan.files:
        if kind == "preserve" and path.exists():
            continue
        if path.exists():
            try:
                current = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if comparable(current) == comparable(content):
                continue
            diff = difflib.unified_diff(
                current.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile="%s (current)" % path,
                tofile="%s (new)" % path,
            )
        else:
            diff = difflib.unified_diff(
                [],
                content.splitlines(keepends=True),
                fromfile="%s (does not exist)" % path,
                tofile="%s (new)" % path,
            )
        info("")
        for line in diff:
            text = line.rstrip("\n")
            if text.startswith("+"):
                info(TERM.green(text))
            elif text.startswith("-"):
                info(TERM.red(text))
            else:
                info(text)


def main(argv=None):
    global TERM

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.no_color:
        TERM = Term(enabled=False)

    if args.dry_run and args.install:
        info(TERM.yellow(
            "note: --dry-run wins over --install; nothing will be written."
        ))

    settings, plat = resolve_settings(args, parser)

    # Interactive is the default when the user gave us nothing to work with.
    gave_identity = any(
        getattr(args, key, None) is not None
        for key in ("fnal_user", "key_default", "config_file")
    )
    interactive = args.interactive or (not args.batch and not gave_identity)

    if interactive and not sys.stdin.isatty():
        fail("interactive mode needs a terminal. Pass --fnal-user and --key-default "
             "(see --help), or use --config-file.")

    if settings["key_default"] is None:
        settings["key_default"] = find_default_key(settings["ssh_dir"])
    if settings["fnal_user"] is None and not interactive:
        guess = os.environ.get("USER") or os.environ.get("USERNAME")
        if guess:
            warn("no --fnal-user given; assuming %r from the environment" % guess)
            settings["fnal_user"] = guess
        else:
            fail("--fnal-user is required (or use --interactive)")

    if interactive:
        settings = run_interactive(settings, plat, settings["ssh_dir"])

    if args.templates_dir:
        templates_dir = expand(args.templates_dir)
        if not templates_dir.is_dir():
            fail("templates directory not found: %s" % templates_dir)
    else:
        templates_dir = find_templates_dir()
        if templates_dir is None:
            fail("could not find the templates directory. Looked in:\n%s\n"
                 "        Pass --templates-dir to point at it explicitly."
                 % "\n".join("          %s" % p for p in template_search_path()))

    install = args.install
    if args.output_dir:
        out_dir = expand(args.output_dir)
    elif install:
        out_dir = settings["ssh_dir"]
    else:
        out_dir = Path.cwd() / "mu2e-ssh-config"

    # ---- key verification -------------------------------------------------
    if not args.no_verify_keys:
        step("Verifying key files")
        checks = [(settings["key_default"], "default")]
        if "github" in settings["groups"]:
            checks.append((settings.get("key_github") or settings["key_default"], "github"))
            checks.append((settings.get("key_fnal") or settings["key_default"], "fnal gitlab"))

        seen = set()
        problems = []
        for path, label in checks:
            if path in seen:
                continue
            seen.add(path)
            if check_key(path, label, require=True):
                ok("%-12s %s" % (label + ":", path))
            else:
                problems.append((label, path))

        if problems:
            info("")
            info("One or more key files are missing. Either generate a key:")
            info("")
            info("    ssh-keygen -t ed25519 -f %s -C \"%s@$(hostname)\""
                 % (settings["key_default"], settings["fnal_user"] or "you"))
            info("")
            info("point the script at an existing key with --key-default, or re-run")
            info("with --no-verify-keys to write the config anyway.")
            info("")
            if args.dry_run:
                warn("continuing anyway because this is a dry run")
            elif args.force:
                warn("continuing anyway because --force was given")
            elif interactive:
                if not prompt_yes_no("Continue with the missing key(s) anyway?", False):
                    fail("aborted; no files were changed", code=2)
            else:
                fail("aborted; no files were changed "
                     "(use --force or --no-verify-keys to override)", code=2)
    else:
        warn("skipping key verification (--no-verify-keys)")

    # ---- render -----------------------------------------------------------
    if all(name in settings["groups"] for name in CONFLICTING_GROUPS):
        winner = ("daq", settings["daq_account"]) \
            if settings.get("gateway_precedence", "daq") == "daq" \
            else ("shift", settings["shift_account"])
        warn(
            "the 'mu2edaq' and 'controlroom' groups both match 'Host mu2egateway*' "
            "with different accounts; ssh takes the first, so the gateways will use "
            "%s. Change this with --gateway-precedence." % winner[1]
        )

    kerberos_groups = [n for n in KERBEROS_ONLY_GROUPS if n in settings["groups"]]
    if kerberos_groups and not settings["features"]["gssapi"]:
        warn(
            "gssapi is off, but the %s group(s) are enabled. Those hosts accept "
            "Kerberos only, so their own blocks still request it -- the rest of "
            "the config will not. Run kinit before connecting."
            % ", ".join(kerberos_groups)
        )

    try:
        plan = assemble(settings, plat, out_dir, templates_dir)
    except TemplateError as exc:
        fail("template error: %s" % exc)

    show_summary(settings, plat, out_dir, install)

    existing = plan.scan_existing()

    info(TERM.bold("Files to be written:"))
    for path, content, kind in plan.files:
        note = ""
        if kind == "preserve":
            note = "  (only if absent)" if not path.exists() else "  (exists, leaving alone)"
        elif path in plan.unchanged:
            note = "  (already up to date)"
        elif path in existing:
            note = "  (exists, will be replaced)"
        info("  %s%s" % (path, note))
    info("")

    # ---- existing files ---------------------------------------------------
    if existing:
        info(TERM.yellow(TERM.bold("WARNING: existing ssh configuration found")))
        info("")
        info("These files already exist and differ from what would be written:")
        for path in existing:
            try:
                size = path.stat().st_size
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
                info("    %s  (%d bytes, modified %s)" % (path, size, when))
            except OSError:
                info("    %s" % path)
        info("")
        if args.no_backup:
            info(TERM.red("  --no-backup was given: these files will be REPLACED "
                          "with no copy kept."))
        else:
            info("  They will be copied to a backup directory first.")
        info("")

    # ---- dry run ----------------------------------------------------------
    if args.dry_run:
        step("Dry run -- nothing will be written")
        if existing and not args.no_backup:
            backup_dir = (
                expand(args.backup_dir) if args.backup_dir
                else out_dir / ("backup-%s" % timestamp())
            )
            backup_existing(existing, backup_dir, dry_run=True)
        write_files(plan, dry_run=True)
        if args.diff:
            show_diff(plan)
        if args.print_only:
            for path, content, kind in plan.files:
                info("")
                info(TERM.bold("----- %s -----" % path))
                info(content)
        info("")
        info("Re-run without --dry-run to write these files%s."
             % ("" if install else ", or add --install to put them in %s" % settings["ssh_dir"]))
        return 0

    # ---- confirm ----------------------------------------------------------
    if existing and not args.force:
        if interactive or sys.stdin.isatty():
            action = "REPLACED with no backup" if args.no_backup else "backed up and replaced"
            if not prompt_yes_no(
                "Continue? Existing files will be %s." % action, not args.no_backup
            ):
                fail("aborted; no files were changed", code=2)
        else:
            fail("existing ssh configuration found in %s and --force was not given; "
                 "aborting without changing anything.\n"
                 "        Run with --dry-run --diff to see what would change." % out_dir,
                 code=2)

    # ---- write ------------------------------------------------------------
    if install:
        secure_ssh_dir(out_dir, dry_run=False)

    if existing and not args.no_backup:
        backup_dir = (
            expand(args.backup_dir) if args.backup_dir
            else out_dir / ("backup-%s" % timestamp())
        )
        backup_existing(existing, backup_dir, dry_run=False)
    elif existing and args.no_backup:
        warn("replacing %d existing file(s) with no backup" % len(existing))

    step("Writing configuration")
    try:
        write_files(plan, dry_run=False)
    except OSError as exc:
        fail("could not write files: %s" % exc)

    if settings["features"]["controlmaster"] and install:
        conn_dir = settings["ssh_dir"] / "connections"
        try:
            conn_dir.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(str(conn_dir), 0o700)
            ok("created %s for ControlMaster sockets" % conn_dir)
        except OSError as exc:
            warn("could not create %s: %s" % (conn_dir, exc))

    # ---- validate ---------------------------------------------------------
    main_path = out_dir / MAIN_CONFIG_FILE
    if not args.no_validate:
        step("Validating with the ssh client")
        # In include layout the generated config points at ~/.ssh/config_*.
        # Those files only exist there once installed, so validating a staged
        # copy would test the wrong thing.  ssh ignores missing Include targets
        # silently, which means this still exercises the main file's syntax.
        if validate_with_ssh(main_path):
            ok("ssh parsed %s" % main_path)
        else:
            info("")
            info("The files were written, but ssh could not parse them.")
            info("Restore your previous configuration from the backup directory")
            info("if you need to get back to a working state.")
            return 1

    # ---- next steps -------------------------------------------------------
    info("")
    info(TERM.green(TERM.bold("Done.")))
    info("")
    if not install:
        info("The files were staged in %s -- nothing in %s was touched."
             % (out_dir, settings["ssh_dir"]))
        info("Review them, then either copy them into place yourself or re-run")
        info("with --install.")
    else:
        info("Try it out:")
        info("")
        info("    ssh -G mu2edaq09.fnal.gov | head       # show the resolved settings")
        info("    ssh mu2edaq09.fnal.gov                 # connect through the gateway")
        if "github" in settings["groups"]:
            info("    ssh -T git@github.com                  # check the GitHub key")
        info("")
        if settings["layout"] == "include":
            info("Put your own host entries in %s/%s; mu2e-ssh-setup never"
                 % (settings["ssh_dir"], USER_CONFIG_FILE))
            info("overwrites that file.")
    if _WARNINGS:
        info("")
        info(TERM.yellow("%d warning(s) were issued above." % len(_WARNINGS)))
    info("")
    info("Full documentation: SSH-HOWTO.md")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\naborted by user", file=sys.stderr)
        sys.exit(130)
