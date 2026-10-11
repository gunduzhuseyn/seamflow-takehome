from collections.abc import Callable

from app.core.clerk import ClerkUserNotFoundError
from app.storage.client import ObjectNotFoundError

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


class FakeStorage:
    """In-memory Storage. `objects` maps a key to its bytes and content type."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.bucket_ready = False

    async def presign_put(self, key: str, content_type: str, expires_s: int) -> str:
        return f"https://storage.test/put/{key}?type={content_type}&exp={expires_s}"

    async def presign_get(self, key: str, expires_s: int) -> str:
        return f"https://storage.test/get/{key}?exp={expires_s}"

    async def head(self, key: str) -> int | None:
        stored = self.objects.get(key)
        return None if stored is None else len(stored[0])

    async def get_bytes(self, key: str) -> bytes:
        try:
            return self.objects[key][0]
        except KeyError:
            raise ObjectNotFoundError(key) from None

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def ensure_bucket(self) -> None:
        self.bucket_ready = True
