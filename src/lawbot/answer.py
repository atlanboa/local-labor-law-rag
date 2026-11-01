from lawbot.models import Answer, Chunk


def answer(question: str, chunks: list[Chunk]) -> Answer:
    raise NotImplementedError
