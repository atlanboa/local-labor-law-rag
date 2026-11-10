import argparse

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from lawbot import config
from lawbot.answer import NO_CHUNKS_TEXT, generate, iso
from lawbot.search import search

app = FastAPI(title="lawbot")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class Citation(BaseModel):
    number: int
    id: str
    title: str
    effective_date: str
    pending_effective_dates: list[str]
    text: str


class AskResponse(BaseModel):
    reply: str
    citations: list[Citation]
    retrieved: list[str]
    disclaimer: str
    seconds: float | None


@app.post("/api/ask")
def ask(request: AskRequest) -> AskResponse:
    question = request.question.strip()
    chunks = search(question, config.TOP_K)
    if not chunks:
        return AskResponse(reply=NO_CHUNKS_TEXT, citations=[], retrieved=[], disclaimer=config.DISCLAIMER, seconds=None)
    try:
        reply, cited, stats = generate(question, chunks)
    except httpx.HTTPError as error:
        raise HTTPException(502, f"Ollama 호출 실패: {type(error).__name__}") from error
    citations = [
        Citation(
            number=number,
            id=chunks[number - 1].id,
            title=chunks[number - 1].title,
            effective_date=iso(chunks[number - 1].effective_date),
            pending_effective_dates=[iso(day) for day in chunks[number - 1].pending_effective_dates],
            text=chunks[number - 1].text,
        )
        for number in cited
    ]
    return AskResponse(
        reply=reply,
        citations=citations,
        retrieved=[chunk.id for chunk in chunks],
        disclaimer=config.DISCLAIMER,
        seconds=round(stats.seconds, 1),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="serve", description="웹 화면용 HTTP API를 띄운다")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    uvicorn.run(app, host="127.0.0.1", port=args.port)
