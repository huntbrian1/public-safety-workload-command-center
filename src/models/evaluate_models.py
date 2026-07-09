from __future__ import annotations

from src import config


def collate_model_notes() -> None:
    parts = ["# Modeling Summary", ""]
    for name in ["model_methodology.md", "model_evaluation.md", "deep_learning_model_evaluation.md", "cluster_methodology.md"]:
        path = config.MEMO_OUTPUT_DIR / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
            parts.append("")
    (config.MEMO_OUTPUT_DIR / "modeling_summary.md").write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    collate_model_notes()
