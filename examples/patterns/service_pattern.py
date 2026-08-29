from typing import Protocol


class UserRepository(Protocol):
    def get(self, user_id: int) -> dict | None: ...


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def get_user(self, user_id: int) -> dict | None:
        return self.repository.get(user_id)
