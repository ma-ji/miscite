from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

from server.miscite.config import Settings
from server.miscite.sources.retractionwatch_sync import sync_retractionwatch_dataset


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()

    parser = argparse.ArgumentParser(description="Sync Retraction Watch dataset to local CSV.")
    parser.add_argument("--force", action="store_true", help="Download even if local file is fresh.")
    args = parser.parse_args()

    result = sync_retractionwatch_dataset(settings, force=args.force)
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

