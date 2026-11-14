"""All domain exceptions live here."""


class OkhteinError(Exception):
    """Base class for every error this application raises on purpose."""


class LLMError(OkhteinError):
    """The language model could not produce an answer (network, auth, rate limit, bad output)."""


class ConfigurationError(OkhteinError):
    """A required setting is missing or invalid."""


class MessagingError(OkhteinError):
    """The messaging gateway (WhatsApp) could not deliver or acknowledge a message."""
