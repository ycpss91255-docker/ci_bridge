#!/usr/bin/env python3
import sys
import tomllib
from pathlib import Path


def main() -> None:
    config_path = Path(sys.argv[1])
    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)

    for section, values in config.items():
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            print(f"{section}\t{key}\t{value}")


if __name__ == "__main__":
    main()
