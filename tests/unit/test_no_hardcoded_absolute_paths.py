from pathlib import Path


def test_no_developer_home_paths_in_portable_files():
    root = Path(__file__).parents[2]
    offenders = []
    for relative in ("src", "configs", "tests", "docs"):
        for path in root.joinpath(relative).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".yml", ".md"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if ("/" + "Users/") in text or ("C:" + "\\Users\\") in text:
                    offenders.append(str(path.relative_to(root)))
    assert offenders == []
