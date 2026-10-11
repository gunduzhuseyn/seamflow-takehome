from collections.abc import Callable

from app.core.clerk import ClerkUserNotFoundError

# Signature of the `make_token` fixture: make_token(sub, *, azp, expires_in, key).
TokenFactory = Callable[..., str]


class FakeClerk:
    """In-memory ClerkClient. Tests add users to `emails` by Clerk user id."""

    def __init__(self) -> None:
        self.emails: dict[str, str] = {}
        self.created: list[str] = []

    async def get_user(self, clerk_user_id: str) -> str:
        try:
            return self.emails[clerk_user_id]
        except KeyError:
            raise ClerkUserNotFoundError(clerk_user_id) from None

    async def get_or_create_user(self, email: str, password: str) -> str:
        for clerk_user_id, known in self.emails.items():
            if known == email:
                return clerk_user_id
        clerk_user_id = f"user_fake{len(self.emails)}"
        self.emails[clerk_user_id] = email
        self.created.append(email)
        return clerk_user_id
