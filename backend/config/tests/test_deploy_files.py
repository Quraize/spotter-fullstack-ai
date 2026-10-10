"""
Deployment contract: the stack must stay inside its own compose project and never touch other services
on the host. The server this ships to also runs an unrelated production project.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
COMPOSE = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
DEPLOY_SH = (REPO / "deploy" / "deploy.sh").read_text(encoding="utf-8")


def test_compose_project_has_a_fixed_unique_name_so_it_never_collides_with_another_stack():
    # Without `name:` the project is named after the directory ("spotter"), which another stack could share;
    # every container, network and volume is namespaced by this.
    assert re.search(r"^name: spotter-assessment$", COMPOSE, re.M)


def test_every_service_is_capped_in_memory_and_cpu():
    services = re.findall(r"^  (\w+):\n", COMPOSE, re.M)
    assert services == ["backend", "web"]
    limits = re.findall(r"limits:\n\s+memory: (\S+)\n\s+cpus: \"(\S+)\"", COMPOSE)
    assert len(limits) == len(services), "each service needs deploy.resources.limits with memory and cpus"


def test_deploy_script_only_runs_scoped_compose_commands():
    docker_calls = re.findall(r"^\s*docker\s+(\S+)(.*)$", DEPLOY_SH, re.M)
    assert docker_calls, "no docker commands found"
    assert {sub for sub, _ in docker_calls} == {"compose"}
    for _, rest in docker_calls:
        assert "--remove-orphans" not in rest
        assert "--pull" not in rest, "pulling base images can change what other stacks build from"
        assert not re.search(r"\b(down|rm|prune|kill|stop)\b", rest)


# --- The port guard, executed for real with stubbed docker and ss --------------------------------


def bash() -> str:
    """Git Bash on Windows (never the WSL launcher in System32), /bin/bash elsewhere."""
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("bash")
    if not found or "system32" in found.lower():
        pytest.skip("bash is not available")
    return found


STUB_DOCKER = """#!/usr/bin/env bash
# Records the compose subcommands deploy.sh issues and stops at the first build.
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  "compose version") exit 0 ;;
  "compose ps -q web") printf '%s' "${STUB_WEB_ID:-}" ;;
  "compose build"*) echo "build reached"; exit 42 ;;
  *) exit 0 ;;
esac
"""

STUB_SS = """#!/usr/bin/env bash
# `ss -ltnH 'sport = :PORT'` prints one LISTEN line when the port is busy.
[ "${STUB_PORT_BUSY:-0}" = 1 ] && echo "LISTEN 0 4096 0.0.0.0:8080 0.0.0.0:* users:((nginx,pid=1,fd=6))"
exit 0
"""


@pytest.fixture
def deploy_tree(tmp_path: Path) -> Path:
    (tmp_path / "deploy").mkdir()
    for name in ("deploy.sh", "smoke.sh"):
        shutil.copy(REPO / "deploy" / name, tmp_path / "deploy" / name)
    (tmp_path / ".env").write_text(
        f"TOMTOM_API_KEY=stub-key\nDJANGO_SECRET_KEY={'k' * 60}\nDJANGO_ALLOWED_HOSTS=203.0.113.10\nWEB_PORT=8080\n",
        encoding="utf-8",
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("docker", STUB_DOCKER), ("ss", STUB_SS)):
        path = stubs / name
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    return tmp_path


def run_deploy(tree: Path, **stub_env: str) -> subprocess.CompletedProcess:
    log = tree / "docker.log"
    env = {
        **os.environ,
        "PATH": f"{tree / 'stubs'}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG": str(log),
        **stub_env,
    }
    result = subprocess.run(
        [bash(), "deploy/deploy.sh", "--no-pull"], cwd=tree, env=env, capture_output=True, text=True, timeout=60
    )
    result.docker_log = log.read_text(encoding="utf-8") if log.exists() else ""
    return result


def test_deploy_refuses_to_start_when_another_service_owns_the_port(deploy_tree: Path):
    result = run_deploy(deploy_tree, STUB_PORT_BUSY="1")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Port 8080 is already in use by another service" in result.stderr
    assert "WEB_PORT" in result.stderr
    assert "compose build" not in result.docker_log, "nothing may be built or started once the guard trips"
    assert "compose up" not in result.docker_log


def test_deploy_proceeds_when_the_port_is_held_by_its_own_web_container(deploy_tree: Path):
    result = run_deploy(deploy_tree, STUB_PORT_BUSY="1", STUB_WEB_ID="abc123")

    assert result.returncode == 42, result.stdout + result.stderr
    assert "build reached" in result.stdout


def test_deploy_proceeds_when_the_port_is_free(deploy_tree: Path):
    result = run_deploy(deploy_tree)

    assert result.returncode == 42, result.stdout + result.stderr
    assert "docker compose build\n" in result.docker_log
