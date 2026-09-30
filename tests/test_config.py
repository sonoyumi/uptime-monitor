from pathlib import Path

import pytest

from uptime_monitor.config import ConfigError, load_monitors, load_settings

EXAMPLE = Path(__file__).resolve().parents[1] / "monitors.example.toml"


def write(tmp_path, text: str) -> Path:
    path = tmp_path / "monitors.toml"
    path.write_text(text)
    return path


def test_example_file_is_valid():
    monitors = load_monitors(EXAMPLE)
    assert [m.kind for m in monitors] == ["http", "http", "tcp", "tls"]
    site, api, dns, cert = monitors
    assert site.keyword == "Example Domain" and site.fail_threshold == 3 and site.max_latency_ms == 5000
    assert api.interval == 120 and api.expect_status == (200,)
    assert (dns.host, dns.port) == ("1.1.1.1", 53) and cert.cert_days == 14 and cert.interval == 3600


def test_defaults_and_single_status_code(tmp_path):
    path = write(
        tmp_path,
        '[defaults]\ninterval = 30\n[[monitor]]\nname = "A"\ntype = "http"\nurl = "http://a.it"\n'
        'expect_status = 301\nmethod = "head"',
    )
    [m] = load_monitors(path)
    assert m.interval == 30 and m.expect_status == (301,) and m.method == "HEAD"


def test_all_errors_at_once(tmp_path):
    path = write(
        tmp_path,
        """
[[monitor]]
name = "Web"
type = "http"
url = "example.com"
[[monitor]]
name = "Db"
type = "tcp"
host = "db"
[[monitor]]
type = "ping"
[[monitor]]
name = "Fast"
type = "http"
url = "https://x.it"
interval = 5
colour = "red"
[[monitor]]
name = "Codes"
type = "http"
url = "https://x.it"
expect_status = ["ok"]
[[monitor]]
name = "Web"
type = "tls"
host = "x.it"
port = 443
""",
    )
    with pytest.raises(ConfigError) as err:
        load_monitors(path)
    text = "\n".join(err.value.errors)
    assert "monitor «Web»: url must start with http" in text
    assert "monitor «Db»: host and port are required" in text
    assert "monitor #3: type must be one of http, tcp, tls; name is required" in text
    assert "monitor «Fast»: unknown keys: colour; interval must be at least 10 seconds" in text
    assert "monitor «Codes»: expect_status must be" in text
    assert len(err.value.errors) == 5  # the second «Web» is valid, but its twin failed: no duplicate report


def test_duplicates_syntax_and_empty(tmp_path):
    dup = write(
        tmp_path,
        '[[monitor]]\nname="A"\ntype="tcp"\nhost="h"\nport=1\n[[monitor]]\nname="A"\ntype="tcp"\nhost="h"\nport=2',
    )
    with pytest.raises(ConfigError, match="duplicate monitor name «A»"):
        load_monitors(dup)
    with pytest.raises(ConfigError, match="TOML syntax error"):
        load_monitors(write(tmp_path, "[[monitor]\nname="))
    with pytest.raises(ConfigError, match="nothing to watch"):
        load_monitors(write(tmp_path, "[defaults]\ninterval = 60"))
    with pytest.raises(ConfigError, match="file not found"):
        load_monitors(tmp_path / "missing.toml")


def test_settings_from_env(monkeypatch):
    for name in (
        "MONITORS_FILE",
        "DATABASE_PATH",
        "BOT_TOKEN",
        "CHAT_ID",
        "HOST",
        "PORT",
        "RETENTION_DAYS",
        "STATUS_TITLE",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("BOT_TOKEN", "1:secret")
    s = load_settings(env_file=None)
    assert s.port == 8090 and str(s.monitors_file) == "monitors.toml" and "1:secret" not in repr(s)
    monkeypatch.setenv("PORT", "eighty")
    with pytest.raises(ValueError, match="PORT"):
        load_settings(env_file=None)
