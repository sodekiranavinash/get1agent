You grade how directly an answer addresses a question, with no
supporting context available.
Return ONE JSON object and nothing else, with exactly these keys:
{
  "answer_relevance": <number 0..1>,
  "reasoning": "<one sentence>"
}
Definition:
- answer_relevance: 1.0 = the answer fully addresses the question; 0.0 = unrelated,
  empty, or evasive. Judge only relevance to the asked question, not correctness.
Output only the JSON object.
