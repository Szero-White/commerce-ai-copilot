"""Check that the text index and the vectors match the documents. Exit code 1 when something is stale.

    python -m scripts.check_index
"""
import json

from app.config import Settings
from app.storage import Store


def main():
    settings = Settings()
    model = settings.embedding_model if settings.embedding_provider != "off" else None
    report = Store(settings.data_path).consistency_report(model)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
