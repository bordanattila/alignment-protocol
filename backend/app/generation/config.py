"""Server-only environment settings, following the existing CONSENSUS_DB_PATH pattern."""
from dataclasses import dataclass, field
import ipaddress
import math
import os
from typing import Mapping
from urllib.parse import urlsplit

from pydantic import SecretStr


class ConfigurationError(Exception):
    def __init__(self):
        super().__init__('Invalid scenario generation configuration')


def boolean(value: str) -> bool:
    if value.lower() not in ('true', 'false'):
        raise ConfigurationError()
    return value.lower() == 'true'


@dataclass(frozen=True)
class GenerationSettings:
    enabled: bool = False
    endpoint: str | None = field(default=None, repr=False)
    model: str | None = field(default=None, repr=False)
    api_key: SecretStr | None = field(default=None, repr=False)
    require_api_key: bool = True
    timeout_seconds: float = 15.0
    response_format: str = 'json_schema'

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.require_api_key) is not bool
                or type(self.timeout_seconds) not in (int, float)
                or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 120
                or self.response_format not in ('json_schema', 'json_object')):
            raise ConfigurationError()
        for value, limit in ((self.endpoint, 2048), (self.model, 200)):
            if value is not None and (not isinstance(value, str) or len(value) > limit
                                      or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ConfigurationError()
        if self.api_key is not None and not isinstance(self.api_key, SecretStr):
            raise ConfigurationError()
        if self.endpoint:
            try:
                url = urlsplit(self.endpoint)
                local = url.hostname == 'localhost'
                if url.hostname:
                    try: local |= ipaddress.ip_address(url.hostname).is_loopback
                    except ValueError: pass
                if (not url.hostname or url.scheme not in ('http', 'https')
                        or url.username is not None or url.password is not None or url.query or url.fragment
                        or (url.scheme == 'http' and not local)):
                    raise ConfigurationError()
                _ = url.port
            except ValueError:
                raise ConfigurationError() from None
        if self.api_key:
            value = self.api_key.get_secret_value()
            if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ConfigurationError()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None):
        env = os.environ if environ is None else environ
        try:
            key = env.get('CONSENSUS_LLM_API_KEY', '').strip()
            return cls(
                enabled=boolean(env.get('CONSENSUS_LLM_ENABLED', 'false').strip()),
                endpoint=env.get('CONSENSUS_LLM_ENDPOINT', '').strip() or None,
                model=env.get('CONSENSUS_LLM_MODEL', '').strip() or None,
                api_key=SecretStr(key) if key else None,
                require_api_key=boolean(env.get('CONSENSUS_LLM_REQUIRE_API_KEY', 'true').strip()),
                timeout_seconds=float(env.get('CONSENSUS_LLM_TIMEOUT_SECONDS', '15')),
                response_format=env.get('CONSENSUS_LLM_RESPONSE_FORMAT', 'json_schema').strip(),
            )
        except (ValueError, TypeError):
            raise ConfigurationError() from None
