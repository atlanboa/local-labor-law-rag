import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
CHROMA_DIR = ROOT / "data" / "chroma"
COLLECTION = "law-chunks"
QUESTIONS_PATH = ROOT / "eval" / "questions.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
BASELINE_PATH = ROOT / "eval" / "baseline.json"

OLLAMA_URL = os.environ.get("LAWBOT_OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = "bge-m3:latest"
CHAT_MODEL = os.environ.get("LAWBOT_CHAT_MODEL", "gemma4:12b-it-q4_K_M")
NUM_CTX = 8192
TOP_K = 5

JUDGE_MODEL = "claude-haiku-5-5"

DISCLAIMER = "이 답변은 법률 자문이 아닙니다. 실제 사안은 노무사나 고용노동부(국번 없이 1350)에 문의하세요."
