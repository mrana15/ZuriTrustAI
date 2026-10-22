"""Configuration from environment variables (see .env.example)."""
from __future__ import annotations

import os
import secrets
import warnings
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


PLACEHOLDER_PREFIXES = ("replace", "change-me", "changeme", "example", "test", "secret")
MIN_SECRET_LENGTH = 32


class ConfigError(ValueError):
    """Raised when production settings are missing or unsafe."""


def _is_weak_secret(value: str) -> bool:
    v = value.strip().lower()
    return len(v) < MIN_SECRET_LENGTH or v.startswith(PLACEHOLDER_PREFIXES)


@dataclass
class Config:
    # "production" turns unsafe-default warnings into hard start-up errors.
    env: str = field(default_factory=lambda: _env("ZURI_ENV", "development").lower())
    # Number of reverse proxies in front of the app whose X-Forwarded-For can be trusted (0 = none).
    trusted_proxies: int = field(default_factory=lambda: int(_env("ZURI_TRUSTED_PROXIES", "0")))
    hmac_secret: str = field(default_factory=lambda: _env("ZURI_HMAC_SECRET"))
    emergency_number: str = field(default_factory=lambda: _env("ZURI_EMERGENCY_NUMBER", "112"))
    audit_log_path: str = field(default_factory=lambda: _env("ZURI_AUDIT_LOG", "logs/audit.jsonl"))
    session_ttl_seconds: int = field(default_factory=lambda: int(_env("ZURI_SESSION_TTL", "1800")))
    kb_min_score: float = field(default_factory=lambda: float(_env("ZURI_KB_MIN_SCORE", "0.25")))
    rate_limit_per_minute: int = field(default_factory=lambda: int(_env("ZURI_RATE_LIMIT", "30")))
    model_threshold: float = field(default_factory=lambda: float(_env("ZURI_MODEL_THRESHOLD", "0.85")))
    tracks_db: str = field(default_factory=lambda: _env("ZURI_TRACKS_DB", "var/tracks.sqlite3"))
    # Hand-off to Zuri Circle licensed health professionals
    telehealth_contact: str = field(default_factory=lambda: _env("ZURI_TELEHEALTH_CONTACT"))
    handoff_webhook: str = field(default_factory=lambda: _env("ZURI_HANDOFF_WEBHOOK"))
    # Bearer token for /api/insights (unset = endpoint disabled)
    admin_token: str = field(default_factory=lambda: _env("ZURI_ADMIN_TOKEN"))
    # WhatsApp Business Cloud API
    wa_verify_token: str = field(default_factory=lambda: _env("WHATSAPP_VERIFY_TOKEN"))
    wa_access_token: str = field(default_factory=lambda: _env("WHATSAPP_ACCESS_TOKEN"))
    wa_phone_number_id: str = field(default_factory=lambda: _env("WHATSAPP_PHONE_NUMBER_ID"))
    wa_app_secret: str = field(default_factory=lambda: _env("WHATSAPP_APP_SECRET"))
    wa_api_version: str = field(default_factory=lambda: _env("WHATSAPP_API_VERSION", "v21.0"))

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def __post_init__(self) -> None:
        if self.is_production:
            self._validate_production()
        elif not self.hmac_secret or _is_weak_secret(self.hmac_secret):
            warnings.warn(
                "ZURI_HMAC_SECRET is missing or a placeholder; using a random per-process secret "
                "(development only). Set ZURI_ENV=production to enforce a real secret.",
                RuntimeWarning,
                stacklevel=2,
            )
            self.hmac_secret = secrets.token_hex(32)

    def _validate_production(self) -> None:
        problems = []
        if not self.hmac_secret or _is_weak_secret(self.hmac_secret):
            problems.append(f"ZURI_HMAC_SECRET must be a random value of at least {MIN_SECRET_LENGTH} characters, not a placeholder")
        if self.whatsapp_enabled:
            if not self.wa_app_secret or _is_weak_secret(self.wa_app_secret):
                problems.append("WHATSAPP_APP_SECRET is required so webhook signatures are verified")
            if not self.wa_verify_token or len(self.wa_verify_token) < 16:
                problems.append("WHATSAPP_VERIFY_TOKEN must be set (at least 16 characters)")
        if self.admin_token and len(self.admin_token) < MIN_SECRET_LENGTH:
            problems.append(f"ZURI_ADMIN_TOKEN must be at least {MIN_SECRET_LENGTH} characters")
        if self.handoff_webhook and not self.handoff_webhook.startswith("https://"):
            problems.append("ZURI_HANDOFF_WEBHOOK must use https://")
        if self.trusted_proxies < 0:
            problems.append("ZURI_TRUSTED_PROXIES cannot be negative")
        if problems:
            raise ConfigError("Unsafe production configuration: " + "; ".join(problems))

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.wa_access_token and self.wa_phone_number_id)
