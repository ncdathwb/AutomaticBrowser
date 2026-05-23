import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILENAME = "proxy_config.json"


@dataclass(frozen=True)
class ProxyConfig:
    enabled: bool = False
    type: str = "http"
    host: str = ""
    port: int = 8080
    username: str = ""
    password: str = ""


def _config_path(data_dir: Path) -> Path:
    return data_dir / CONFIG_FILENAME


def load_proxy_config(data_dir: Path) -> ProxyConfig:
    path = _config_path(data_dir)
    if not path.is_file():
        return ProxyConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProxyConfig(
            enabled=bool(data.get("enabled", False)),
            type=data.get("type", "http"),
            host=str(data.get("host", "")),
            port=int(data.get("port", 8080)),
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
        )
    except (json.JSONDecodeError, OSError, ValueError):
        return ProxyConfig()


def save_proxy_config(config: ProxyConfig, data_dir: Path) -> bool:
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        _config_path(data_dir).write_text(
            json.dumps(
                {
                    "enabled": config.enabled,
                    "type": config.type,
                    "host": config.host,
                    "port": config.port,
                    "username": config.username,
                    "password": config.password,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def build_proxy_arg(config: ProxyConfig) -> str:
    if not config.enabled or not config.host.strip():
        return ""
    scheme = config.type if config.type in ("http", "https", "socks4", "socks5") else "http"
    return f"--proxy-server={scheme}://{config.host.strip()}:{config.port}"
