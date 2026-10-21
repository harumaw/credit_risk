class NotFoundError(Exception):
    """Сущность не найдена в базе данных."""


class AlreadyExistsError(Exception):
    """Сущность с такими уникальными полями уже существует."""

    def __init__(self, field: str | None = None):
        super().__init__(field)
        self.field = field  # какое уникальное поле совпало: email / inn_fl / phone


class InvalidCredentailsError(Exception):
    """Неверный email или пароль."""


class UserBlockedError(Exception):
    """Учётная запись заблокирована."""


class ForbiddenError(Exception):
    """Действие запрещено правилами (причина — в тексте)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class FieldValueError(Exception):
    """Значение поля не прошло проверку правил (например, сумма вне условий продукта)."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message
