from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

from server.miscite.core.config import Settings
from server.miscite.sources.predatory_sync import sync_predatory_datasets


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()

    parser = argparse.ArgumentParser(description="Sync predatory journals/publishers lists to local CSV.")
    parser.add_argument("--force", action="store_true", help="Download even if local file is fresh.")
    args = parser.parse_args()

    result = sync_predatory_datasets(settings, force=args.force)
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
