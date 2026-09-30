"""Gate do versionamento automatico (Sprint 20).

- semantic-release no GitHub Actions (`.github/workflows/release.yml` +
  `.releaserc.json`) e' o dono das tags vX.Y.Z, do CHANGELOG, da GitHub
  Release e do `npm publish` do `@wiati/dfe-agent`.
- A base RAG nao e' versionada no git: so' o sha (`storage/dfe.db.gz.sha256`)
  fica no repo; o `.gz` vive na release `rag-base` e e' anexado a cada vX.Y.Z.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
WORKFLOW: Path = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
RELEASERC: Path = PROJECT_ROOT / ".releaserc.json"
ATTACH_SCRIPT: Path = PROJECT_ROOT / ".github" / "scripts" / "attach-rag-base.sh"
SET_VERSION_SCRIPT: Path = PROJECT_ROOT / ".github" / "scripts" / "set_pyproject_version.py"


@pytest.fixture(scope="module")
def releaserc() -> dict[str, Any]:
    return json.loads(RELEASERC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _plugin(releaserc: dict[str, Any], name: str) -> dict[str, Any]:
    for entry in releaserc["plugins"]:
        if entry == name:
            return {}
        if isinstance(entry, list) and entry[0] == name:
            return entry[1]
    raise AssertionError(f"plugin {name} ausente do .releaserc.json")


def test_releaserc_tags_na_main(releaserc: dict[str, Any]) -> None:
    assert releaserc["branches"] == ["main"]
    assert releaserc["tagFormat"] == "v${version}"


def test_releaserc_publica_pacote_npm(releaserc: dict[str, Any]) -> None:
    assert _plugin(releaserc, "@semantic-release/npm")["pkgRoot"] == "packages/dfe-agent"
    _plugin(releaserc, "@semantic-release/github")


def test_releaserc_usa_conventional_commits(releaserc: dict[str, Any]) -> None:
    assert _plugin(releaserc, "@semantic-release/commit-analyzer")["preset"] == "conventionalcommits"


def test_releaserc_commita_arquivos_de_versao(releaserc: dict[str, Any]) -> None:
    git = _plugin(releaserc, "@semantic-release/git")
    assert set(git["assets"]) >= {
        "packages/dfe-agent/package.json",
        "packages/dfe-agent/CHANGELOG.md",
        "pyproject.toml",
    }
    assert "[skip ci]" in git["message"], "commit de release nao pode redisparar o workflow"


def test_releaserc_scripts_existem(releaserc: dict[str, Any]) -> None:
    exec_cfg = _plugin(releaserc, "@semantic-release/exec")
    assert ".github/scripts/set_pyproject_version.py" in exec_cfg["prepareCmd"]
    assert ".github/scripts/attach-rag-base.sh" in exec_cfg["successCmd"]
    # A base e' conferida antes do npm publish / GitHub Release, nao so' depois.
    assert "attach-rag-base.sh --verify" in exec_cfg["verifyConditionsCmd"]
    assert SET_VERSION_SCRIPT.exists() and ATTACH_SCRIPT.exists()


def test_workflow_roda_na_main(workflow: dict[Any, Any]) -> None:
    # PyYAML le a chave `on` como True.
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["branches"] == ["main"]


def test_workflow_release_depende_dos_testes(workflow: dict[Any, Any]) -> None:
    release = workflow["jobs"]["release"]
    assert release["needs"] == "test"
    perms = release["permissions"]
    assert perms["contents"] == "write"
    assert perms["id-token"] == "write", "provenance do npm exige id-token"


def test_workflow_pina_semantic_release(workflow: dict[Any, Any]) -> None:
    run = next(s["run"] for s in workflow["jobs"]["release"]["steps"] if "semantic-release" in str(s.get("run", "")))
    packages = re.findall(r"-p\s+(\S+)", run)
    assert packages, "semantic-release deve ser instalado via `npx -p`"
    for pkg in packages:
        assert re.search(r"@\d+\.\d+\.\d+$", pkg), f"versao sem pin exato: {pkg}"


def test_workflow_usa_secret_npm(workflow: dict[Any, Any]) -> None:
    step = next(s for s in workflow["jobs"]["release"]["steps"] if "semantic-release" in str(s.get("run", "")))
    assert step["env"]["NPM_TOKEN"] == "${{ secrets.NPM_TOKEN }}"


def test_pacote_builda_assets_antes_do_publish() -> None:
    pkg = json.loads((PROJECT_ROOT / "packages" / "dfe-agent" / "package.json").read_text(encoding="utf-8"))
    prepack = pkg["scripts"]["prepack"]
    assert "build" in prepack and "sync" in prepack


def _usable_bash() -> str | None:
    """bash que roda de verdade (no Windows `bash` pode ser o stub do WSL sem distro)."""
    candidates = [shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"]
    for cand in candidates:
        if not cand or not Path(cand).exists():
            continue
        probe = subprocess.run([cand, "-c", "true"], capture_output=True, check=False)
        if probe.returncode == 0:
            return cand
    return None


def test_attach_script_sintaxe_valida() -> None:
    bash = _usable_bash()
    if bash is None:
        pytest.skip("bash indisponivel")
    proc = subprocess.run([bash, "-n", str(ATTACH_SCRIPT)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


# --- base RAG fora do git ---


def _tracked(path: str) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
    )
    return proc.returncode == 0


def test_base_rag_nao_versionada() -> None:
    assert not _tracked("storage/dfe.db.gz"), "dfe.db.gz vive na release `rag-base`, nao no git"
    listed = subprocess.run(
        ["git", "ls-files", "data"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert listed == "", "documentos brutos de data/ nao sao versionados"


def test_sha_da_base_continua_versionado() -> None:
    assert _tracked("storage/dfe.db.gz.sha256"), "o sha e' a 'versao' da base que o CI confere"


@pytest.mark.parametrize("path", ["storage/dfe.db.gz", "data/abc.bin", "data/abc.pdf"])
def test_gitignore_cobre_base_rag(path: str) -> None:
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path], cwd=PROJECT_ROOT, check=False
    )
    assert proc.returncode == 0, f"{path} deveria estar no .gitignore"


# --- set_pyproject_version.py ---


def _load_set_version() -> ModuleType:
    spec = importlib.util.spec_from_file_location("set_pyproject_version", SET_VERSION_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_set_version_troca_so_a_versao_do_projeto() -> None:
    mod = _load_set_version()
    text = '[project]\nname = "dfe-agent"\nversion = "0.1.0"\n\n[tool.x]\nversion = "9.9.9"\n'
    out = mod.set_version(text, "1.3.0")
    assert 'version = "1.3.0"' in out
    assert 'version = "9.9.9"' in out


@pytest.mark.parametrize("bad", ["1.3", "v1.3.0", "latest", ""])
def test_set_version_rejeita_versao_invalida(bad: str) -> None:
    with pytest.raises(ValueError):
        _load_set_version().set_version('[project]\nversion = "0.1.0"\n', bad)


def test_set_version_exige_linha_version() -> None:
    with pytest.raises(ValueError):
        _load_set_version().set_version('[project]\nname = "x"\n', "1.0.0")


def test_set_version_ignora_version_fora_de_project() -> None:
    text = '[tool.x]\nversion = "9.9.9"\n\n[project]\nname = "d"\nversion = "0.1.0"\n'
    out = _load_set_version().set_version(text, "2.0.0")
    assert '[tool.x]\nversion = "9.9.9"' in out
    assert 'name = "d"\nversion = "2.0.0"' in out


def test_set_version_no_pyproject_real() -> None:
    text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "7.7.7"' in _load_set_version().set_version(text, "7.7.7")


def test_set_version_main_uso_incorreto(capsys: pytest.CaptureFixture[str]) -> None:
    assert _load_set_version().main([]) == 2
