"""Shared safe failure taxonomy; no domain, provider or transport dependencies."""
from enum import StrEnum


class FailureCategory(StrEnum):
    DISABLED = 'disabled'
    CONFIGURATION = 'configuration'
    TIMEOUT = 'timeout'
    UNAVAILABLE = 'unavailable'
    AUTHENTICATION = 'authentication'
    RATE_LIMITED = 'rate_limited'
    QUOTA_EXCEEDED = 'quota_exceeded'
    MODEL_UNAVAILABLE = 'model_unavailable'
    UNSUPPORTED_FORMAT = 'unsupported_format'
    INVALID_PROVIDER_SCHEMA = 'invalid_provider_schema'
    UNSUPPORTED_RESPONSE = 'unsupported_response'
    INVALID_JSON = 'invalid_json'
    INVALID_SCHEMA = 'invalid_schema'
    INVALID_CONTINUITY = 'invalid_continuity'
    REFUSAL = 'refusal'
    UNEXPECTED = 'unexpected'
