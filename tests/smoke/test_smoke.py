from pathlib import Path

import venture_os
from venture_os.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_package_imports():
    assert venture_os.__version__


def test_default_mode_is_replay(monkeypatch):
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert Settings(_env_file=None).llm_mode == "replay"


def test_required_repo_files_exist():
    for name in ["README.md", "LICENSE", ".env.example", "docker-compose.yml"]:
        assert (ROOT / name).is_file(), name


README_HEADINGS = [
    "## Quickstart",
    "## What works and what is mocked",
    "## Architecture",
    "## Models and free resources",
    "## Cost per run",
    "## Demo video",
    "## What our system will NOT do",
    "## How the project stays alive after the hackathon",
]


def test_readme_has_required_headings_in_order():
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    found = [line.strip() for line in lines if line.startswith("## ")]
    assert found == README_HEADINGS


def test_readme_quickstart_and_cost():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = text.split("## Quickstart", 1)[1].split("\n## ", 1)[0]
    assert "```bash\ndocker compose up\n```" in quickstart
    cost = text.split("## Cost per run", 1)[1].split("\n## ", 1)[0]
    assert "$" in cost


def test_compose_runs_app_and_local_model_without_keys():
    import yaml

    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert {"db", "seed", "ollama", "ollama-pull", "api", "ui"} <= set(services)
    assert services["ui"]["ports"][0].endswith(":8501")
    assert "ollama-pull" not in services["api"]["depends_on"]  # the app never waits for the model download
    for name, svc in services.items():
        image = svc.get("image", "")
        assert not image.endswith(":latest") and (":" in image or "build" in svc), f"{name} image not pinned"


def test_env_example_has_no_real_secrets():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith(("LLM_API_KEY=", "ADMIN_TOKEN=")):
            assert line.split("=", 1)[1] in ("", "ollama"), line
