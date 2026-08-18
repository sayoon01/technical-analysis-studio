from __future__ import annotations

from backend.jobs.job_worker import run_worker_forever


def main() -> None:
    run_worker_forever()


if __name__ == "__main__":
    main()
