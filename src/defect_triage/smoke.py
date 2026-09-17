from __future__ import annotations

from tempfile import TemporaryDirectory

from .service import DefectTriageService


def main() -> None:
    with TemporaryDirectory() as directory:
        service = DefectTriageService(database_path=f"{directory}/smoke.db")
        if not service.list_teams() or not service.list_known_errors():
            raise RuntimeError("Seed data was not loaded.")
        print("Database smoke test passed.")


if __name__ == "__main__":
    main()
