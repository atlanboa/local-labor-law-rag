import re

from lawbot.models import Chunk

# Only the top-ranked found chunk's refs are followed (rank 2 and beyond added nothing in the eval).
FOLLOW_RANKS = 1

# Applies to workplaces with fewer than 5 regular workers: 제11조 and its decree and table.
SMALL_WORKPLACE_IDS = ("근로기준법 제11조", "근로기준법 시행령 제7조", "근로기준법 시행령 별표 1")

_HEADCOUNT = re.compile(r"(\d+)\s*(?:명|인)\s*(이하|미만)?")
_WORKPLACE = re.compile(r"사업장|사업체|사업|회사|업체|가게|상시")


def is_small_workplace(question: str) -> bool:
    # A headcount of 4 or fewer ("4명", "4명 이하", "5인 미만") in a question about a workplace.
    if not _WORKPLACE.search(question):
        return False
    for count, bound in _HEADCOUNT.findall(question):
        limit = 5 if bound == "미만" else 4
        if int(count) <= limit:
            return True
    return False


def expand(question: str, found: list[Chunk]) -> list[Chunk]:
    # Chunks to append after found, in the order they should be appended.
    from lawbot.search import get_chunks  # search imports this module

    wanted: list[str] = list(SMALL_WORKPLACE_IDS) if is_small_workplace(question) else []
    for chunk in found[:FOLLOW_RANKS]:
        wanted.extend(chunk.refs)
    have = {chunk.id for chunk in found}
    return get_chunks(chunk_id for chunk_id in dict.fromkeys(wanted) if chunk_id not in have)
