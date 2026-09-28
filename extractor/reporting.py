from pathlib import Path


def save_report(
    path: Path,
    content: str,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        content,
        encoding="utf-8",
    )