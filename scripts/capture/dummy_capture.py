from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dummy capture script for testing the Phenopi scheduler."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the dummy capture file will be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"{timestamp}.txt"

    output_path.touch()

    print(f"[dummy-capture] Wrote {output_path}")


if __name__ == "__main__":
    main()
