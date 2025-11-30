class StonksError(Exception):
    """Base exception for Stonks application."""
    def __init__(self, message: str = "An unexpected error occurred"):
        self.message = message
        super().__init__(self.message)

# --- Not Found Errors (404) ---
class EntityNotFoundError(StonksError):
    """Base for Not Found errors."""
    pass

class TickerNotFoundError(EntityNotFoundError):
    def __init__(self, message: str = "Ticker not found"):
        super().__init__(message)

class UserNotFoundError(EntityNotFoundError):
    def __init__(self, message: str = "User not found"):
        super().__init__(message)

class ApiKeyNotFoundError(EntityNotFoundError):
    def __init__(self, message: str = "API Key not found"):
        super().__init__(message)

class OrderNotFoundError(EntityNotFoundError):
    def __init__(self, message: str = "Order not found"):
        super().__init__(message)

# --- Already Exists Errors (400/409) ---
class EntityAlreadyExistsError(StonksError):
    pass

class TickerAlreadyExistsError(EntityAlreadyExistsError):
    def __init__(self, message: str = "Ticker already exists"):
        super().__init__(message)

class UserAlreadyExistsError(EntityAlreadyExistsError):
    def __init__(self, message: str = "User already exists"):
        super().__init__(message)

class HumanETFAlreadyListedError(EntityAlreadyExistsError):
    def __init__(self, message: str = "You have already listed your Human ETF."):
        super().__init__(message)


# --- Authentication/Authorization Errors (401/403) ---
class AuthError(StonksError):
    pass

class InvalidCredentialsError(AuthError):
    def __init__(self, message: str = "Incorrect email or password"):
        super().__init__(message)

class PermissionDeniedError(AuthError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message)

class UserInactiveError(AuthError):
    def __init__(self, message: str = "Inactive user"):
        super().__init__(message)

class ApiKeyRevokedError(AuthError):
    def __init__(self, message: str = "API Key is revoked"):
        super().__init__(message)


# --- Business Logic Errors (400) ---
class BusinessLogicError(StonksError):
    pass

class BailoutNotAllowedError(BusinessLogicError):
    def __init__(self, message: str = "Only bankrupt users can request a bailout."):
        super().__init__(message)

class NoSharesToBailoutError(BusinessLogicError):
    def __init__(self, message: str = "No shares found to bailout."):
        super().__init__(message)

class InvalidDividendRateError(BusinessLogicError):
    def __init__(self, message: str = "Bankrupt users must set dividend rate to at least 50%."):
        super().__init__(message)

class InsufficientSharesToBurnError(BusinessLogicError):
    def __init__(self, message: str = "Insufficient shares to burn."):
        super().__init__(message)

class InsufficientSharesError(BusinessLogicError):
    def __init__(self, owned: float, requested: float, message: str = None):
        if message is None:
            message = f"Insufficient shares (Owned: {owned}, Requested: {requested})"
        super().__init__(message)

class InsufficientBalanceError(BusinessLogicError):
    def __init__(self, required: float, available: float, message_prefix: str = "Insufficient balance", message: str = None):
        if message is None:
            message = f"{message_prefix} (Required: {required}, Available: {available})"
        super().__init__(message)

class MarketPriceNotFoundError(BusinessLogicError):
    def __init__(self, message: str = "Current market price not available."):
        super().__init__(message)

class InvalidLimitOrderPriceError(BusinessLogicError):
    def __init__(self, message: str = "Limit order requires a valid target price."):
        super().__init__(message)

class OrderNotCancellableError(BusinessLogicError):
    def __init__(self, status: str, message: str = None):
        if message is None:
            message = f"Cannot cancel order with status: {status}"
        super().__init__(message)

class BankruptcyNotAllowedError(BusinessLogicError):
    def __init__(self, current_assets: float, message: str = None):
        if message is None:
            message = f"Bankruptcy only allowed when total assets <= 0. Current: {current_assets}"
        super().__init__(message)

# --- System Errors (500) ---
class OrderSystemError(StonksError):
    def __init__(self, original_error: str):
        super().__init__(f"Order system error: {original_error}")
