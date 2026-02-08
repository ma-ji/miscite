from __future__ import annotations

import argparse

from dotenv import load_dotenv

from server.miscite.core.cli import add_runtime_args, apply_runtime_overrides
from server.miscite.core.config import Settings
from server.miscite.core.migrations import (
    assert_db_current,
    create_revision,
    current_heads,
    expected_heads,
    revision_state,
    stamp_head,
    upgrade_to_head,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Database migration helper.")
    add_runtime_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("upgrade", help="Apply all pending migrations.")
    sub.add_parser("check", help="Return 0 when DB is already at migration head.")
    sub.add_parser("current", help="Print current applied DB revision head(s).")
    sub.add_parser("heads", help="Print expected migration head(s) from code.")
    sub.add_parser("stamp-head", help="Stamp database to current head without running migrations.")

    rev = sub.add_parser("revision", help="Create a new migration revision.")
    rev.add_argument("-m", "--message", required=True, help="Revision message.")
    rev.add_argument(
        "--no-autogenerate",
        action="store_true",
        help="Create empty revision instead of autogenerating diff from models.",
    )

    return parser


def main() -> int:
    load_dotenv()
    args = _parser().parse_args()
    apply_runtime_overrides(args)
    settings = Settings.from_env()

    if args.command == "upgrade":
        upgrade_to_head(settings)
        print("ok: upgraded to head")
        return 0

    if args.command == "check":
        try:
            assert_db_current(settings)
        except RuntimeError as exc:
            print(f"pending: {exc}")
            return 1
        except Exception as exc:
            print(f"error: {exc}")
            return 2
        print("ok: at head")
        return 0

    if args.command == "current":
        heads = current_heads(settings)
        print(",".join(heads) if heads else "none")
        return 0

    if args.command == "heads":
        heads = expected_heads(settings)
        print(",".join(heads) if heads else "none")
        return 0

    if args.command == "stamp-head":
        stamp_head(settings)
        state = revision_state(settings)
        print("ok: stamped", ",".join(state.expected_heads) if state.expected_heads else "none")
        return 0

    if args.command == "revision":
        create_revision(
            settings,
            message=args.message,
            autogenerate=not bool(args.no_autogenerate),
        )
        print("ok: revision created")
        return 0

    print(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
