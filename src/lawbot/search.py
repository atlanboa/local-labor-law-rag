from collections.abc import Iterable

from lawbot.models import Chunk


def search(question: str, k: int = 5) -> list[Chunk]:
    raise NotImplementedError


def get_chunks(ids: Iterable[str]) -> list[Chunk]:
    # Same order as ids; unknown ids are skipped.
    raise NotImplementedError
