#!/usr/bin/python3

import os, getpass
import abc
from colorama import Fore, Style
import io
import subprocess
import sys
from dataclasses import dataclass
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
    def non_bail_exec(cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True)

    # may exit
    @staticmethod
    def exec(cmd: str) -> str:
        completed_process = Utils.non_bail_exec(cmd)
        if completed_process.returncode != 0:
            Utils.bail(f"Failed to push: cmd `{cmd}` failed: {completed_process.stderr.rstrip()}", color=Fore.MAGENTA)
        return completed_process.stdout
    
    # may exit when pred may exit
    @staticmethod
    def check(pred: Callable[[], bool], description: str) -> bool:
        Utils.cprint(f"    {description}", file=sys.stderr, color=Fore.YELLOW)
        ok = pred()
        if ok:
            Utils.cprint("      OK", file=sys.stderr, color=Fore.MAGENTA)
        else:
            Utils.cprint("      KO", file=sys.stderr, color=Fore.MAGENTA)
        return ok

    # FIXME: handle panic
    # FIXME: flesh out fn
    @staticmethod
    def commit_hashes_between(fst: str, lst: str) -> List[str]:
        return Utils.exec(f"'git rev-list --reverse --topo-order {fst}..{lst}'").splitlines()


@dataclass
class Commit:
    hash: str
    _code_basepath: Optional[str]
    updated_files: List[str]
    deleted_files: List[str]
    new_files: List[str]

    # FIXME: handle_panic
    def code_basepath(self) -> Optional[str]:
        return self._code_basepath

    # FIXME: handle panic
    # FIXME: flesh out fn
    @staticmethod
    def from_hash(c_hash: str) -> "Commit":
        return Commit(c_hash, None, [], [], [])

    # FIXME: handle panic
    # FIXME: remove code basedir on destruction (or directly handled by tmp dir)
    # FIXME: flesh out fn
    def __del__(self):
        pass


@dataclass
class Ref:
    name: str
    commits: List[Commit]


@dataclass
class PreReceiveContext:
    refs: List[Ref]

    @staticmethod
    def from_stdin() -> "PreReceiveContext":
        return PreReceiveContext.from_reader(sys.stdin)

    # FIXME: handle panic
    @staticmethod
    def from_reader(r: io.TextIOBase) -> "PreReceiveContext":
        ctx = PreReceiveContext([])

        line = r.readline()
        while line:
            [old_value, new_value, ref_name] = line.split()
            commit_hashes = Utils.commit_hashes_between(old_value, new_value)
            commits = [Commit.from_hash(c_hash) for c_hash in commit_hashes]
            ref = Ref(ref_name, commits)
            ctx.refs.append(ref)
            line = r.readline()

        return ctx


def rust_hook():
    def run_tests(commit: Commit) -> bool:
        (_, _, ok) = Utils.non_bail_exec()
        return ok

    def check_fmt_on_lst_commit(ref: Ref) -> bool:
        files_to_fmt = set()
        for commit in ref.commits:
            files_to_fmt.update(commit.updated_files + commit.new_files)
            files_to_fmt.difference_update(commit.deleted_files)

        (_, _, ok) = Utils.non_bail_exec()
        return ok

    ctx = PreReceiveContext.from_stdin()
    print(ctx, flush=True)
    for ref in ctx.refs:
        if ref.name == "refs/heads/master":

            print("rustfmt --check", file=sys.stderr)
            if not Utils.check(
                lambda ref=ref: check_fmt_on_lst_commit(ref), f"{ref.commits[-1].hash}"
            ):
                Utils.bail("fmt failed")

            print("cargo test --release", file=sys.stderr)
            for commit in ref.commits:
                if not Utils.check(
                    lambda commit=commit: run_tests(commit), f"{commit.hash}"
                ):
                    Utils.bail(f"tests failed on commit {commit}")


def test1():
    mock_input = io.StringIO(
        "old_value new_value ref_name\nold_value2\tnew_value2  ref_name2"
    )
    print(f"context mock input={PreReceiveContext.from_reader(mock_input)}")


def main():
    print("main")
    print(f"context from stdin={PreReceiveContext.from_stdin()}")


if __name__ == "__main__":
    # main()
    # test1()
    print("Entering pre-receive hook", flush=True)
    print("Env thinks the user is [%s]" % (os.getlogin()), flush=True)
    print("Effective user is [%s]" % (getpass.getuser()), flush=True)

    rust_hook()
    exit(1)
