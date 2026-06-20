"""
`mycel-demo` — lay the bundled MICE demo down on disk so it can be run.

    mycel-demo init [target]     copy the demo assets into ./target (default: ./mycel-demo)

The assets (data, node configs, OPA policies, registry, docker-compose stack)
ship inside the package. `init` materializes them into a working directory
because docker-compose needs real files on disk:

    pip install mycel[demo]
    mycel-demo init ./mice
    cd mice && cp .env.example .env   # add your HF_TOKEN
    docker compose up                 # nodes + connectors + OPA sidecars
    mycel-ui                          # dashboard → http://localhost:7860
"""

import argparse
import shutil
import sys
from pathlib import Path

from mycel.demo import ASSETS

_DEFAULT_TARGET = "mycel-demo"


def _init(target: Path, force: bool) -> int:
    if not ASSETS.is_dir():
        print(
            f"demo assets not found at {ASSETS} — is the [demo] extra installed?",
            file=sys.stderr,
        )
        return 1
    if target.exists() and any(target.iterdir()) and not force:
        print(
            f"{target} already exists and is not empty; pass --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    # copytree with dirs_exist_ok so --force can refresh an existing checkout
    shutil.copytree(ASSETS, target, dirs_exist_ok=True)

    print(f"Demo scaffolded into {target}/")
    print("Next:")
    print(f"  cd {target}")
    print("  cp .env.example .env        # add your HF_TOKEN")
    print("  docker compose up           # build first: docker build -t mycel:latest <mycel source>")
    print("  mycel-ui                    # dashboard → http://localhost:7860")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mycel-demo", description="Scaffold the bundled Mycel (MICE) demo."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="copy the demo assets into a directory")
    init.add_argument(
        "target",
        nargs="?",
        default=_DEFAULT_TARGET,
        help=f"destination directory (default: ./{_DEFAULT_TARGET})",
    )
    init.add_argument(
        "--force", action="store_true", help="overwrite an existing directory"
    )

    args = parser.parse_args(argv)
    if args.command == "init":
        return _init(Path(args.target), args.force)
    parser.error(f"unknown command {args.command!r}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
