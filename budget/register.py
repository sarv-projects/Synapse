"""Per-model RPM/RPD/TPM register for the Budget Controller."""
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelBudget:
    model_id: str
    rpm_limit: int
    tpm_limit: int
    rpd_limit: int

    # Internal RPM tracking (60s sliding window — Groq does not expose per-minute in headers)
    rpm_requests: list[float] = field(default_factory=list)
    rpm_remaining: int = 0

    # From response headers (x-ratelimit-remaining-requests = daily)
    rpd_remaining: int = 0
    rpd_reset: float = 0.0  # epoch seconds

    # From response headers (x-ratelimit-remaining-tokens = per-minute)
    tpm_remaining: int = 0
    tpm_reset: float = 0.0  # epoch seconds

    # Advisory — extrapolated from TPM consumption
    tpd_remaining: int = 0

    # Tokens-in-flight estimation
    tokens_in_flight: int = 0

    # Gemini-specific (shared TPM pool)
    provider: str = "groq"
    shared_tpm_pool: Optional[str] = None

    def __post_init__(self):
        self.rpm_remaining = self.rpm_limit
        self.rpd_remaining = self.rpd_limit
        self.tpm_remaining = self.tpm_limit
        self.tpd_remaining = self.tpd_limit

    @property
    def tpd_limit(self) -> int:
        return self.tpm_limit * 60 * 24

    def record_rpm(self, now: float | None = None) -> None:
        now = now or datetime.now(UTC).timestamp()
        cutoff = now - 60.0
        self.rpm_requests = [t for t in self.rpm_requests if t >= cutoff]
        self.rpm_requests.append(now)
        self.rpm_remaining = max(0, self.rpm_limit - len(self.rpm_requests))

    def update_from_headers(self, headers: dict) -> None:
        now = datetime.now(UTC).timestamp()
        if "x-ratelimit-remaining-requests" in headers:
            self.rpd_remaining = int(headers["x-ratelimit-remaining-requests"])
        if "x-ratelimit-reset-requests" in headers:
            self.rpd_reset = float(headers["x-ratelimit-reset-requests"])
        if "x-ratelimit-remaining-tokens" in headers:
            self.tpm_remaining = int(headers["x-ratelimit-remaining-tokens"])
        if "x-ratelimit-reset-tokens" in headers:
            self.tpm_reset = float(headers["x-ratelimit-reset-tokens"])

    def can_afford(self, estimated_tokens: int) -> bool:
        now = datetime.now(UTC).timestamp()
        self.record_rpm(now)
        if self.rpm_remaining <= 0:
            return False
        if self.rpd_remaining <= 0:
            return False
        if self.tpm_remaining < estimated_tokens + self.tokens_in_flight:
            return False
        return True

    def reserve(self, estimated_tokens: int) -> None:
        self.tokens_in_flight += estimated_tokens

    def release(self, actual_tokens: int) -> None:
        self.tokens_in_flight = max(0, self.tokens_in_flight - actual_tokens)
        self.tpm_remaining = max(0, self.tpm_remaining - actual_tokens)
        self.rpd_remaining = max(0, self.rpd_remaining - 1)


class BudgetRegister:
    """Per-model budget state. Persisted to DynamoDB."""

    def __init__(self):
        self.models: dict[str, ModelBudget] = {}
        self._init_groq_models()

    def _init_groq_models(self):
        groq = [
            ("llama-3.1-8b-instant", 30, 6000, 14400),
            ("meta-llama/llama-4-scout-17b-16e-instruct", 30, 30000, 1000),
            ("llama-3.3-70b-versatile", 30, 6000, 1000),
            ("openai/gpt-oss-20b", 30, 8000, 1000),
            ("openai/gpt-oss-120b", 30, 8000, 1000),
            ("qwen-qwq-32b", 60, 6000, 1000),
        ]
        for mid, rpm, tpm, rpd in groq:
            self.models[mid] = ModelBudget(
                model_id=mid, rpm_limit=rpm, tpm_limit=tpm, rpd_limit=rpd, provider="groq"
            )

    def get(self, model_id: str) -> ModelBudget:
        if model_id not in self.models:
            self.models[model_id] = ModelBudget(
                model_id=model_id, rpm_limit=30, tpm_limit=6000, rpd_limit=1000
            )
        return self.models[model_id]

    def snapshot(self) -> dict:
        return {
            mid: {
                "rpm_remaining": m.rpm_remaining,
                "rpd_remaining": m.rpd_remaining,
                "tpm_remaining": m.tpm_remaining,
                "rpm_limit": m.rpm_limit,
                "rpd_limit": m.rpd_limit,
                "tpm_limit": m.tpm_limit,
                "tokens_in_flight": m.tokens_in_flight,
            }
            for mid, m in self.models.items()
        }
