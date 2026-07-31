"""CLI: process one uploaded source by id."""

from __future__ import annotations

import argparse

from backend.api.deps import get_source_service


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    args = parser.parse_args()
    result = get_source_service().process(args.source_id)
    print(result)


if __name__ == "__main__":
    main()
