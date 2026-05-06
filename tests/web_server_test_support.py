from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]


def write_complete_collected_case(case_dir: Path) -> None:
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text("{}\n", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")


def load_web_module():
    from query_doctor.web import server

    return server
