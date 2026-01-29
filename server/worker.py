from __future__ import annotations

import multiprocessing as mp

from dotenv import load_dotenv

from server.miscite.config import Settings
from server.miscite.worker import run_worker_loop


def _run_single(process_index: int) -> None:
    settings = Settings.from_env()
    run_worker_loop(settings, process_index=process_index)


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()

    processes = max(1, settings.worker_processes)
    if processes == 1:
        _run_single(0)
        return

    ctx = mp.get_context("spawn")
    children: list[mp.Process] = []
    for i in range(processes):
        p = ctx.Process(target=_run_single, args=(i,), daemon=False)
        p.start()
        children.append(p)

    for p in children:
        p.join()


if __name__ == "__main__":
    main()

