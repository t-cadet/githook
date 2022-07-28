import abc
import io
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional


# FIXME: this class is only used as a namespace
class Utils(abc.ABC):
    @staticmethod
    def bail(msg: str):
        pass

    @staticmethod
    def non_bail_exec() -> (str, str, bool):
        return ("", "", True)

    # FIXME: flesh out fn
    @staticmethod
    def exec() -> str:
        pass

    # FIXME: flesh out fn
    @staticmethod
    def check(pred: Callable[[], bool], description: str, color=None) -> bool:
        print(f"    {description}", file=sys.stderr)
        ok = pred()
        if ok:
            print("      OK")
        else:
            print("      KO")
        return ok

    # FIXME: handle panic
    # FIXME: flesh out fn
    @staticmethod
    def commit_hashes_between(fst: str, lst: str) -> List[str]:
        return [fst]


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

        while line := r.readline():
            [old_value, new_value, ref_name] = line.split()
            commit_hashes = Utils.commit_hashes_between(old_value, new_value)
            commits = [Commit.from_hash(c_hash) for c_hash in commit_hashes]
            ref = Ref(ref_name, commits)
            ctx.refs.append(ref)

        return ctx


def rust_hook():
    def run_tests(commit: Commit) -> bool:
        (_, _, ok) = Utils.non_bail_exec()
        return True

    def check_fmt_on_lst_commit(ref: Ref) -> bool:
        files_to_fmt = set()
        for commit in ref.commits:
            files_to_fmt.update(commit.updated_files + commit.new_files)
            files_to_fmt.difference_update(commit.deleted_files)

        (_, _, ok) = Utils.non_bail_exec()
        return ok

    ctx = PreReceiveContext.from_stdin()
    for ref in ctx.refs:
        if ref.name == "refs/head/master":

            print("rustfmt --check")
            if not Utils.check(
                lambda ref=ref: check_fmt_on_lst_commit(ref), f"{ref.commits[-1].hash}"
            ):
                Utils.bail("fmt failed")

            print("cargo test --release")
            for commit in ref.commits:
                if not Utils.check(
                    lambda commit=commit: run_tests(commit), f"{commit.hash}"
                ):
                    Utils.bail(f"tests failed on commit {commit}")


def test1():
    mock_input = io.StringIO(
        "old_value new_value ref_name\nold_value2\tnew_value2  ref_name2"
    )
    print(f"{PreReceiveContext.from_reader(mock_input)=}")


def main():
    print("main")
    print(f"{PreReceiveContext.from_stdin()=}")


if __name__ == "__main__":
    # main()
    # test1()
    rust_hook()
