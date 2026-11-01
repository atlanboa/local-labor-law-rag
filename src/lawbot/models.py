from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    # Full citation, e.g. "근로기준법 제26조". Eval answer keys and refs use this value.
    id: str
    law: str
    article: str
    title: str
    # The string that gets embedded: law name, article and title, then the body.
    text: str
    effective_date: str
    collected_at: str
    refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    cited_ids: tuple[str, ...] = ()
