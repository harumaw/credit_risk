class NotFoundError(Exception):
    """Сущность не найдена в базе данных."""


class AlreadyExistsError(Exception):
    """Сущность с такими уникальными полями уже существует."""

class InvalidCredentailsError(Exception):
    """Неверный email или пароль."""