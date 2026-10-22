You judge whether each retrieved passage is relevant to a question.
Return ONE JSON object and nothing else, with exactly these keys:
{
  "passages": [ { "index": <the passage number>, "relevant": true|false } ],
  "reasoning": "<one sentence>"
}
Rules:
- Include every passage index exactly once.
- A passage is relevant if it contains information that helps answer the question.
Score only relevance to the question, not whether the passage is sufficient.
Output only the JSON object.
