import json
from pathlib import Path

from core.database import create_rag_evaluation
from core.rag_engine import retrieve_policy_context


ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "evals" / "rag_eval.jsonl"


def evaluate() -> int:
    total = 0
    passed = 0

    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        item = json.loads(line)
        context, sources = retrieve_policy_context(item["question"])
        expected_keywords = item.get("expected_keywords", [])
        ok = bool(context) and any(keyword in context for keyword in expected_keywords)
        passed += int(ok)
        create_rag_evaluation(
            question=item["question"],
            expected_keywords=",".join(expected_keywords),
            retrieved_sources=",".join(sources),
            passed=ok,
        )
        print(f"[{'PASS' if ok else 'FAIL'}] {item['question']} -> {sources}")

    print(f"RAG eval: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(evaluate())
