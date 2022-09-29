#!/usr/bin/python3

# Git hook documentation
# from https://git-scm.com/docs/githooks
#
# pre-receive
#
# This hook is invoked by git-receive-pack[1] when it reacts to git push and updates reference(s) in its repository. Just before starting to update refs on the remote repository, the pre-receive hook is invoked. Its exit status determines the success or failure of the update.
# This hook executes once for the receive operation. It takes no arguments, but for each ref to be updated it receives on standard input a line of the format:
#
# <old-value> SP <new-value> SP <ref-name> LF
#
# where <old-value> is the old object name stored in the ref, <new-value> is the new object name to be stored in the ref and <ref-name> is the full name of the ref. When creating a new ref, <old-value> is the all-zeroes object name.
# If the hook exits with non-zero status, none of the refs will be updated. If the hook exits with zero, updating of individual refs can still be prevented by the update hook.
# Both standard output and standard error output are forwarded to git send-pack on the other end, so you can simply echo messages for the user.
# The number of push options given on the command line of git push --push-option=... can be read from the environment variable GIT_PUSH_OPTION_COUNT, and the options themselves are found in GIT_PUSH_OPTION_0, GIT_PUSH_OPTION_1,…​If it is negotiated to not use the push options phase, the environment variables will not be set. If the client selects to use push options, but doesn’t transmit any, the count variable will be set to zero, GIT_PUSH_OPTION_COUNT=0.
#
# See the section on "Quarantine Environment" in git-receive-pack[1] for some caveats.

import os, getpass
import abc
from tempfile import TemporaryDirectory
from colorama import Fore, Style
import io
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

# FIXME: this class is only used as a namespace
class Utils(abc.ABC):
    @staticmethod
    def cprint(msg: str, file=sys.stdout, color="", style=""):
        for line in msg.splitlines():
            print(f"{color}{style}{line}{Style.RESET_ALL}", file=file)

    # always exit
    @staticmethod
    def bail(msg: str, exit_code = 1, color="", style=""):
        Utils.cprint(msg, color=color, style=style, file=sys.stderr)
        exit(exit_code)

    @staticmethod
    def non_bail_exec(cmd: str, cwd=None) -> subprocess.CompletedProcess:
        return subprocess.run(f"set -eufo pipefail;{cmd}", shell=True, capture_output=True, text=True, executable="/bin/bash", cwd=cwd)

    # may exit
    @staticmethod
    def exec(cmd: str, cwd=None) -> str:
        completed_process = Utils.non_bail_exec(cmd, cwd)
        if completed_process.returncode != 0:
            Utils.bail(f"Failed to push: cmd `{cmd}` failed: {completed_process.stderr.rstrip()}", color=Fore.MAGENTA)
        return completed_process.stdout
    
    # may exit when pred may exit
    @staticmethod
    def check(pred: Callable[[], bool], description: str) -> bool:
        print(f"      {description}", file=sys.stderr)
        ok = pred()
        if ok:
            Utils.cprint("        OK", file=sys.stderr, color=Fore.GREEN)
        else:
            Utils.cprint("        KO", file=sys.stderr, color=Fore.RED)
        return ok


@dataclass
class Commit:
    hash: str
    _code_basedir: Optional[TemporaryDirectory]
    updated_files: List[str]
    deleted_files: List[str]
    new_files: List[str]
    datetime: str
    short_hash: str
    author: str
    subject: str
    body: str

    def code_basedir(self) -> TemporaryDirectory:  # type: ignore
        if self._code_basedir:
            return self._code_basedir
        
        basedir = TemporaryDirectory(prefix=self.hash, dir=HOOK_BUILD_DIR)

        # extract source code
        Utils.exec(f"git archive {self.hash} | tar -x -C {basedir.name}")

        # make sure the compiler does not ignore updated files
        Utils.exec(f"touch {' '.join(self.updated_files)}", cwd=basedir.name)
        
        self._code_basedir = basedir
        return self._code_basedir
    
    def display(self) -> str:
        return f"{Fore.YELLOW}{self.subject} ({self.short_hash}){Style.RESET_ALL}"

    # may exit
    @staticmethod
    def hashes_between(fst: str, lst: str) -> List[str]:
        return Utils.exec(f"git rev-list --reverse --topo-order {fst}..{lst}").splitlines()        


    # may exit when parsing git diff-tree output
    @staticmethod
    def from_hash(c_hash: str) -> "Commit":
        SEP = "»¦«" # unlikely to find this str in a commit
        [datetime, short_hash, author, subject, body] = Utils.exec(f"git log -n1 --pretty=%ai{SEP}%h{SEP}%an{SEP}%s{SEP}%b {c_hash}").rstrip().split(SEP)
        
        c =  Commit(c_hash, None, [], [], [], datetime, short_hash, author, subject, body)
        
        status_and_paths = Utils.exec(f"git diff-tree -z --no-commit-id --name-status -r {c_hash}").rstrip("\x00").split("\x00")
        for i in range(0, len(status_and_paths), 2):
            status, path = status_and_paths[i], status_and_paths[i+1]
            if status == "A":
                c.new_files.append(path)
            elif status == "D":
                c.deleted_files.append(path)
            elif status == "M":
                c.updated_files.append(path)
            else:
                Utils.bail(f"unexpected status {status} for file {path}", color=Fore.MAGENTA)
        return c


@dataclass
class Ref:
    name: str
    commits: List[Commit]


@dataclass
class PreReceiveContext:
    refs: List[Ref] = field(default_factory=list)

    @staticmethod
    def from_stdin() -> "PreReceiveContext":
        return PreReceiveContext.from_reader(sys.stdin)  # type: ignore

    # may exit on readline, Utils.commit_hashes_between or Commit.from_hash
    @staticmethod
    def from_reader(r: io.TextIOBase) -> "PreReceiveContext":
        ctx = PreReceiveContext()

        for line in r:
            [old_value, new_value, ref_name] = line.split()
            commit_hashes = Commit.hashes_between(old_value, new_value)
            commits = [Commit.from_hash(c_hash) for c_hash in commit_hashes]
            ref = Ref(ref_name, commits)
            ctx.refs.append(ref)

        return ctx

# FIXME: handle exceptions
def rust_hook():
    def run_tests(commit: Commit) -> bool:
        target_dir = commit.code_basedir().name
        ok = Utils.non_bail_exec(f"unset GIT_QUARANTINE_PATH; cargo test --release --target-dir {target_dir}", cwd=target_dir).returncode == 0
        return ok

    def check_fmt_on_lst_commit(ref: Ref) -> bool:
        files_to_fmt = set()
        for commit in ref.commits:
            files_to_fmt.update(commit.updated_files + commit.new_files)
            files_to_fmt.difference_update(commit.deleted_files)
        
        if not files_to_fmt:
            return True

        target_dir = ref.commits[-1].code_basedir().name
        ok = Utils.non_bail_exec(f"rustfmt --edition 2021 --check {' '.join(files_to_fmt)}", cwd=target_dir).returncode == 0
        return ok

    Utils.cprint("Entering pre-receive hook", file=sys.stderr, color=Fore.MAGENTA)
    ctx = PreReceiveContext.from_stdin()
    for ref in ctx.refs:
        if ref.name == "refs/heads/master":
            Utils.cprint(f"  Running checks on {ref.name}", file=sys.stderr, color=Fore.MAGENTA)
            print("    rustfmt --check", file=sys.stderr)
            if not Utils.check(
                lambda ref=ref: check_fmt_on_lst_commit(ref), f"{ref.commits[-1].display()}"
            ):
                Utils.bail("fmt failed")

            print("    cargo test --release", file=sys.stderr)
            for commit in ref.commits:
                if not Utils.check(
                    lambda commit=commit: run_tests(commit), f"{commit.display()}"
                ):
                    Utils.bail(f"tests failed on commit {commit}")
    Utils.cprint("Pre-receive hook success", file=sys.stderr, color=Fore.MAGENTA)
    print(ctx, flush=True)


# def test1():
#     mock_input = io.StringIO(
#         "old_value new_value ref_name\nold_value2\tnew_value2  ref_name2"
#     )
#     print(f"context mock input={PreReceiveContext.from_reader(mock_input)}")


def main():
    print("main")
    print(f"context from stdin={PreReceiveContext.from_stdin()}")

 # The owner of this folder is the user that pushes
 # So we need to enable RW group rights 
 # To allow the hook to write when other users push
print(os.environ)
HOOK_BUILD_DIR = f"{os.environ['GIT_DIR']}/hooks/pre_receive_hook_tmp_build_dir"
Utils.exec(f"mkdir -m=775 -p {HOOK_BUILD_DIR}")

if __name__ == "__main__":
    # main()
    # test1()
    # print("Entering pre-receive hook", flush=True)
    # print("Env thinks the user is [%s]" % (os.getlogin()), flush=True)
    # print("Effective user is [%s]" % (getpass.getuser()), flush=True)

    rust_hook()
    exit(1)
