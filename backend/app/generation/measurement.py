"""Content-free optional measurements shared by the existing private diagnostics."""
from collections.abc import Callable
import re
import time
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator, model_serializer

Duration = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Tokens = Annotated[int, Field(ge=0, le=1_000_000_000, strict=True)]
RejectionDetail = Literal['repeated_title', 'repeated_content', 'duplicate_choice_text', 'identical_effects']


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    input_tokens: Tokens | None = None
    output_tokens: Tokens | None = None
    total_tokens: Tokens | None = None

    @model_validator(mode='after')
    def consistent(self):
        if self.input_tokens is not None and self.output_tokens is not None and self.total_tokens is not None:
            if self.input_tokens + self.output_tokens != self.total_tokens:
                raise ValueError('Inconsistent usage')
        if self.total_tokens is not None and any(v is not None and v>self.total_tokens for v in (self.input_tokens,self.output_tokens)):
            raise ValueError('Inconsistent usage')
        return self


def extract_usage(raw) -> TokenUsage | None:
    if not isinstance(raw, dict): return None
    # Never copy arbitrary provider metadata, nested details or error messages.
    names = {'input_tokens':'prompt_tokens', 'output_tokens':'completion_tokens', 'total_tokens':'total_tokens'}
    try:
        usage = TokenUsage(**{key:raw.get(value) for key,value in names.items()})
        return usage if any(v is not None for v in usage.model_dump().values()) else None
    except (ValidationError, ValueError, TypeError): return None


class GenerationMeasurement(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    version: Literal[1] = 1
    operation: Literal['crisis', 'endgame']
    model: str | None = Field(default=None, max_length=200, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]*$')
    provider_attempted: bool
    provider_seconds: Duration | None = None
    validation_seconds: Duration | None = None
    fallback_seconds: Duration | None = None
    # Commit and browser delivery occur after this record is frozen; unknown.
    availability_seconds: Duration | None = None
    usage: TokenUsage | None = None
    history_available: bool
    reference_count: int | None = Field(default=None, ge=0, le=10, strict=True)
    rejection_detail: RejectionDetail | None = None


class MeasuredDiagnostic(BaseModel):
    # Old five-field records serialize unchanged and remain immutable on save.
    measurement: GenerationMeasurement | None = None

    @model_serializer(mode='wrap')
    def serialize(self, handler):
        data = handler(self)
        if self.measurement is None: data.pop('measurement', None)
        return data


class GenerationTrace:
    def __init__(self, settings, operation, history_available, clock: Callable[[], float] = time.perf_counter):
        self.clock = clock
        self.operation = operation
        model = settings.model
        secret = settings.api_key.get_secret_value() if settings.api_key else None
        self.model = model if isinstance(model,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}',model) and not (secret and secret in model) else None
        self.history_available = history_available
        self.provider_attempted = False
        self.provider_seconds = self.validation_seconds = self.fallback_seconds = None
        self.usage = None
        self.reference_count = None
        self.rejection_detail = None

    async def call(self, provider, request):
        started = self.clock(); self.provider_attempted = True
        try:
            response = await provider.generate(request)
            usage = getattr(response, 'usage', None)
            if isinstance(usage, TokenUsage): self.usage = usage
            return response
        except Exception as error:
            if getattr(error, 'provider_attempted', None) is False: self.provider_attempted = False
            usage = getattr(error, 'usage', None)
            if isinstance(usage, TokenUsage): self.usage = usage
            raise
        finally:
            self.provider_seconds = round(max(0.0, self.clock()-started),6) if self.provider_attempted else None

    def validate(self, function):
        started = self.clock()
        try: return function()
        finally: self.validation_seconds = round(max(0.0, self.clock()-started),6)

    def fallback(self, function):
        started = self.clock()
        try: return function()
        finally: self.fallback_seconds = round(max(0.0, self.clock()-started),6)

    def measurement(self):
        return GenerationMeasurement(operation=self.operation, model=self.model, provider_attempted=self.provider_attempted,
            provider_seconds=self.provider_seconds, validation_seconds=self.validation_seconds,
            fallback_seconds=self.fallback_seconds, usage=self.usage, history_available=self.history_available,
            reference_count=self.reference_count, rejection_detail=self.rejection_detail)
