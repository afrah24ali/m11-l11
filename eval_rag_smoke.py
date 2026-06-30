"""RAG smoke evaluator -- 3 pre-shipped questions, binary PASS/FAIL per question.

The Lab smoke evaluator proves the grounding-check logic that the Integration's
RAG grounding-rate harness scales up. It is binary by design (PASS/FAIL per
question, exit 0 iff all PASS); it does not aggregate a rate, and it does NOT
apply decline-exclusion -- the three smoke questions are all answerable
against the seeded fixtures, so a decline at the Lab tier is a defect.

Grounding-check methodology (Lab smoke):

  A response is grounded iff (a) response.citations has length >= 1 AND
  (b) every chunk_id in response.citations is present in the candidate set
  returned by the retrieval call for the same question. The Lab smoke does
  NOT apply decline-exclusion (the Lab's 3 questions are all answerable
  against the seeded Weaviate; decline is not in scope at the Lab tier).

The same paragraph appears in the published Applied Lab page so the
documented methodology and the code that scores against it stay in sync.
"""


import json
import os
from pathlib import Path

import httpx


API_URL = os.environ.get("API_URL", "http://localhost:8000")
SMOKE_PATH = Path("data/rag_smoke.json")


def load_questions(path: str | Path = SMOKE_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def score_grounding(response_body: dict, candidate_ids: set) -> bool:
    citations = response_body.get("citations", [])

    if len(citations) < 1:
        return False

    cited_ids = {citation.get("chunk_id") for citation in citations}
    return all(chunk_id in candidate_ids for chunk_id in cited_ids)


def evaluate_question(question: dict) -> bool:
    response = httpx.post(
        f"{API_URL}/rag/answer",
        json={
            "question": question["question"],
            "k": question.get("k", 4),
        },
        timeout=60.0,
    )
    response.raise_for_status()
    response_body = response.json()

    candidate_ids = {
        chunk["chunk_id"]
        for chunk in response_body["retrieved"]
    }

    return score_grounding(response_body, candidate_ids)


def main() -> int:
    questions = load_questions()
    all_passed = True

    for question in questions:
        passed = evaluate_question(question)
        question_id = question.get("question_id", question.get("id", "unknown"))

        print(f"{question_id}: {'PASS' if passed else 'FAIL'}")

        if not passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())