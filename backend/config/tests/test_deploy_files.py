"""
Deployment contract: the stack must stay inside its own compose project and never touch other services
on the host. The server this ships to also runs an unrelated production project.
"""

import http.server
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import ClassVar

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
  "compose build"*) [ "${STUB_BUILD_OK:-0}" = 1 ] && exit 0; echo "build reached"; exit 42 ;;
  *) exit 0 ;;
esac
"""

STUB_SMOKE = """#!/usr/bin/env bash
echo "smoke $*" >> "$STUB_LOG"
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


# --- The public host must be accepted, not just loopback ---------------------------------------
# The first server deploy passed the loopback smoke test while Django rejected the public IP with a 400
# (DJANGO_ALLOWED_HOSTS was wrong). These pin the checks that catch that before the script reports success.


def test_deploy_refuses_an_allowed_hosts_list_without_a_public_host(deploy_tree: Path):
    env = deploy_tree / ".env"
    env.write_text(env.read_text(encoding="utf-8").replace("203.0.113.10", "localhost,127.0.0.1"), encoding="utf-8")

    result = run_deploy(deploy_tree)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr and "public" in result.stderr
    assert "compose build" not in result.docker_log


def test_deploy_hands_every_configured_public_host_to_the_smoke_test(deploy_tree: Path):
    env = deploy_tree / ".env"
    env.write_text(
        env.read_text(encoding="utf-8").replace("203.0.113.10", "localhost,203.0.113.10,example.test"), encoding="utf-8"
    )
    smoke = deploy_tree / "deploy" / "smoke.sh"
    smoke.write_text(STUB_SMOKE, encoding="utf-8", newline="\n")

    result = run_deploy(deploy_tree, STUB_BUILD_OK="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "smoke http://127.0.0.1:8080 203.0.113.10,example.test\n" in result.docker_log


class StubApp(http.server.BaseHTTPRequestHandler):
    """Just enough of the deployed app for smoke.sh: Django-style 400 for a Host it does not allow."""

    allowed_hosts: ClassVar[frozenset[str]] = frozenset({"127.0.0.1", "localhost"})
    protocol_version = "HTTP/1.1"  # keep-alive, like nginx; the client closes when Content-Length is read

    def log_message(self, *args):  # keep pytest output clean
        pass

    def reply(self, code: int, body: str, content_type: str = "text/html") -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            return self.reply(200, '<!doctype html><html><body><div id="root"></div></body></html>')
        if self.path == "/api/health":
            host = self.headers.get("Host", "").rsplit(":", 1)[0]
            if host not in self.allowed_hosts:
                return self.reply(400, "<h1>Bad Request (400)</h1>")
            return self.reply(200, '{"status":"ok","service":"stub","tomtom_key_configured":true}', "application/json")
        return self.reply(404, "")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/api/plan":
            routes = [{"name": f"Route {n}"} for n in (1, 2, 3)]
            return self.reply(
                200,
                json.dumps({"routes": routes, "recommended_route_id": "r1"}, separators=(",", ":")),
                "application/json",
            )
        return self.reply(404, "")


@pytest.fixture
def stub_app():
    servers = []

    def start(allowed_hosts: set[str]) -> str:
        handler = type("Handler", (StubApp,), {"allowed_hosts": frozenset(allowed_hosts)})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def run_smoke(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [bash(), str(REPO / "deploy" / "smoke.sh"), *args], capture_output=True, text=True, timeout=60
    )


def test_smoke_passes_against_a_healthy_app(stub_app):
    result = run_smoke(stub_app({"127.0.0.1"}))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 routes" in result.stdout


def test_smoke_fails_when_django_rejects_the_public_host(stub_app):
    result = run_smoke(stub_app({"127.0.0.1"}), "203.0.113.10")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "203.0.113.10" in result.stdout
    assert "DJANGO_ALLOWED_HOSTS" in result.stdout


def test_smoke_passes_when_every_public_host_is_accepted(stub_app):
    result = run_smoke(stub_app({"127.0.0.1", "203.0.113.10", "example.test"}), "203.0.113.10,example.test")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "203.0.113.10" in result.stdout and "example.test" in result.stdout


def test_nginx_does_not_duplicate_the_frame_header_django_already_sends():
    # Django's XFrameOptionsMiddleware and nginx's server-level add_header both emit X-Frame-Options: DENY on
    # /api responses (seen on the deployed app); the proxy location must hide the upstream copy.
    nginx = (REPO / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    api_location = re.search(r"location /api/ \{(.*?)\n    \}", nginx, re.S).group(1)
    assert "proxy_hide_header X-Frame-Options;" in api_location


# --- Access log that survives deploys, and the visitor summary built on it -------------------------


def test_web_access_log_is_written_to_a_volume_of_this_stack_and_still_to_stdout():
    # A container's own log dies with it at every rebuild; the access log also goes to a named volume of
    # this project so visitor history survives deploys. stdout stays so `docker compose logs web` works.
    web = re.search(r"^  web:\n(.*?)(?=^  \w+:|^volumes:)", COMPOSE, re.M | re.S).group(1)
    assert re.search(r"^\s+- web-logs:/var/log/spotter$", web, re.M)
    declared = COMPOSE[COMPOSE.index("\nvolumes:") :]
    assert re.search(r"^  web-logs:", declared, re.M)
    nginx = (REPO / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    assert "access_log /var/log/spotter/access.log main;" in nginx
    assert "access_log /var/log/nginx/access.log main;" in nginx


VISITORS_SH = (REPO / "deploy" / "visitors.sh").read_text(encoding="utf-8")
CHROME = "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"


def hit(ip: str, when: str, request: str, status: int, agent: str) -> str:
    """One line in nginx's "main" format as the official image defines it (last field: X-Forwarded-For)."""
    return f'{ip} - - [{when} +0000] "{request} HTTP/1.1" {status} 100 "-" "{agent}" "-"\n'


SAMPLE_LOG = (
    hit("203.0.113.7", "14/Oct/2026:09:12:01", "GET /", 200, CHROME)
    + hit("203.0.113.7", "14/Oct/2026:09:12:02", "GET /assets/index-abc.js", 200, CHROME)
    + hit("203.0.113.7", "14/Oct/2026:09:12:40", "POST /api/plan", 200, CHROME)
    + hit("198.51.100.9", "14/Oct/2026:19:23:37", "GET /.env", 404, "Mozilla/5.0 zgrab/0.x")
    + hit("198.51.100.9", "14/Oct/2026:19:23:38", "GET /wp-login.php", 404, "Mozilla/5.0 zgrab/0.x")
    + hit("172.18.0.1", "14/Oct/2026:08:00:00", "GET /api/health", 200, "curl/8.5.0")
    + "2026/10/14 08:00:00 [notice] 1#1: start worker processes\n"
)


def run_visitors(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [bash(), str(REPO / "deploy" / "visitors.sh"), *args], capture_output=True, text=True, timeout=60
    )


def test_visitors_summarises_the_access_log_per_client(tmp_path: Path):
    log = tmp_path / "access.log"
    log.write_text(SAMPLE_LOG, encoding="utf-8")

    result = run_visitors(str(log))

    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 2, result.stdout
    assert re.search(r"^203\.0\.113\.7\s+3 req\s+1 app\s+1 plans\s+0 404s", lines[0])
    assert "14/Oct/2026:09:12:01 .. 14/Oct/2026:09:12:40" in lines[0]
    assert lines[0].endswith(CHROME)
    assert re.search(r"^198\.51\.100\.9\s+2 req\s+0 app\s+0 plans\s+2 404s", lines[1])
    assert "zgrab" in lines[1]
    assert "172.18.0.1" not in result.stdout, "the smoke test's curl requests are noise"
    assert "notice" not in result.stdout, "nginx error-log lines are not requests"


def test_visitors_merges_several_saved_logs(tmp_path: Path):
    # A copy saved before a deploy plus the volume's file after it: counts add up across files.
    (tmp_path / "a.log").write_text(SAMPLE_LOG, encoding="utf-8")
    (tmp_path / "b.log").write_text(SAMPLE_LOG.splitlines()[2] + "\n", encoding="utf-8")

    result = run_visitors(str(tmp_path / "a.log"), str(tmp_path / "b.log"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(r"^203\.0\.113\.7\s+4 req\s+1 app\s+2 plans", result.stdout, re.M)


def test_visitors_fails_loudly_on_a_missing_log(tmp_path: Path):
    result = run_visitors(str(tmp_path / "nope.log"))

    assert result.returncode != 0
    assert "nope.log" in result.stderr


def test_visitors_only_reads_from_this_stack_when_run_without_arguments():
    docker_calls = re.findall(r"^\s*docker\s+(.*)$", VISITORS_SH, re.M)
    assert docker_calls, "the no-argument form reads the running web container's log"
    for call in docker_calls:
        assert call.startswith("compose exec -T web cat "), call


def test_visitors_says_so_when_only_the_smoke_test_has_called(tmp_path: Path):
    # Right after a deploy the fresh log holds nothing but the smoke test's curl calls; silence looks broken.
    log = tmp_path / "access.log"
    log.write_text(hit("172.18.0.1", "15/Oct/2026:10:40:00", "GET /api/health", 200, "curl/8.5.0"), encoding="utf-8")

    result = run_visitors(str(log))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no visitors" in result.stdout.lower()
