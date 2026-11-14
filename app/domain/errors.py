"""All domain exceptions live here."""


class OkhteinError(Exception):
    """Base class for every error this application raises on purpose."""


class LLMError(OkhteinError):
    """The language model could not produce an answer (network, auth, rate limit, bad output)."""


class ConfigurationError(OkhteinError):
    """A required setting is missing or invalid."""


class MessagingError(OkhteinError):
    """The messaging gateway (WhatsApp) could not deliver or acknowledge a message."""


class TransientLLMError(LLMError):
    """A failure worth retrying: rate limit, server error, timeout, dropped connection."""


class PermanentLLMError(LLMError):
    """A failure that retrying cannot fix: bad API key, unknown model, rejected request."""


class AllProvidersFailedError(LLMError):
    """Every provider in the chain failed. Carries one message per provider for the logs."""

    def __init__(self, failures: list[str]) -> None:
        super().__init__("All LLM providers failed: " + "; ".join(failures))
        self.failures = failures


class InvalidTransitionError(OkhteinError):
    """A state change that the state machine does not allow (for example releasing a bot-active chat)."""
