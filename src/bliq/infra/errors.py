"""Exception hierarchy for bliq."""


class BliqError(Exception):
    """Base for all bliq-specific errors."""


class ConfigError(BliqError):
    """Raised when configuration parsing or validation fails."""


class BinanceAPIError(BliqError):
    """Raised when a Binance REST/WS call returns an unexpected error."""


class RateLimitError(BinanceAPIError):
    """Raised on HTTP 429 or 418 from Binance."""


class SymbolNotFoundError(BinanceAPIError):
    """Raised when a requested symbol is not tradable on the target market."""


class DataIntegrityError(BliqError):
    """Raised when local state cannot be reconciled with upstream data."""


class StorageError(BliqError):
    """Raised when SQLite reads/writes fail."""
