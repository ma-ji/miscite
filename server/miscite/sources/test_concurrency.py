import threading
import time
import unittest

from server.miscite.sources.concurrency import acquire_api_slot


class ApiConcurrencyTests(unittest.TestCase):
    def test_source_cap_is_enforced(self) -> None:
        job_limiter = threading.BoundedSemaphore(4)
        active = 0
        max_active = 0
        lock = threading.Lock()

        def worker() -> None:
            nonlocal active, max_active
            with acquire_api_slot(
                source="openalex-test-source-cap",
                job_limiter=job_limiter,
                source_limit=1,
            ):
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.03)
                with lock:
                    active -= 1

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(max_active, 1)

    def test_job_cap_is_enforced(self) -> None:
        job_limiter = threading.BoundedSemaphore(1)
        active = 0
        max_active = 0
        lock = threading.Lock()

        def worker() -> None:
            nonlocal active, max_active
            with acquire_api_slot(
                source="openalex-test-job-cap",
                job_limiter=job_limiter,
                source_limit=8,
            ):
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.03)
                with lock:
                    active -= 1

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(max_active, 1)
