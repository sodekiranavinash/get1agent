"""Route grounding: an answer may only link pages that exist.

The citation path was already validated against the generated catalogue, but the
answer **text** was not — so the model could write any path it liked and the
widget rendered it as a link. Reported: asked where to import a skill, AI Assistant
read that `/agent-skills` has a *Skills Registry* tab, invented
`/skills-registry` from the tab's name, and sent the reader to a 404.

Two things are pinned here:

* ``sanitize_answer`` — the rewrite rules, including the correcting case (a link
  whose label names a real page) and the code span the widget would otherwise
  linkify.
* ``RouteFilter`` — the streamed path. A link is only judged once it is complete,
  so the filter holds back the construct being written. The critical property is
  that **streaming one character at a time produces exactly the same text as
  sanitising the whole answer**, because a filter that lost a tail would truncate
  every answer in production.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import deep_links


class SanitizeAnswerTests(unittest.TestCase):
    def test_a_link_to_a_real_page_is_untouched(self) -> None:
        text = "Open the [Agent builder](/agent-builder) to change the model."
        self.assertEqual(deep_links.sanitize_answer(text), text)

    def test_an_invented_route_keeps_its_words_and_loses_its_target(self) -> None:
        # The reported case: "Skills Registry" is a *tab* on /agent-skills.
        text = "Open the [Skills Registry](/skills-registry) tab to import one."
        self.assertEqual(
            deep_links.sanitize_answer(text),
            "Open the Skills Registry tab to import one.",
        )

    def test_a_label_that_names_a_real_page_corrects_the_target(self) -> None:
        # A shortened or mistyped route is worth fixing, not dropping.
        self.assertEqual(
            deep_links.sanitize_answer("See [Metrics](/metric)."),
            "See [Metrics](/metrics).",
        )

    def test_a_bare_route_in_brackets_is_unlinked_when_it_does_not_exist(self) -> None:
        self.assertEqual(
            deep_links.sanitize_answer("Go to [/skills-registry]."),
            "Go to /skills-registry.",
        )
        # …and kept when it does, because the widget links it.
        self.assertEqual(
            deep_links.sanitize_answer("Go to [/metrics]."),
            "Go to [/metrics].",
        )

    def test_a_code_span_loses_its_backticks_when_the_route_is_not_real(self) -> None:
        # The widget turns a route-shaped code span into a link, so leaving the
        # backticks would hand the reader the same dead link by another route.
        self.assertEqual(
            deep_links.sanitize_answer("Open `/skills-registry` now."),
            "Open /skills-registry now.",
        )
        self.assertEqual(
            deep_links.sanitize_answer("Open `/metrics` now."),
            "Open `/metrics` now.",
        )

    def test_ordinary_code_is_never_touched(self) -> None:
        text = "Run `pip install uv` and then `uv sync`."
        self.assertEqual(deep_links.sanitize_answer(text), text)

    def test_external_links_and_fragments_are_never_touched(self) -> None:
        text = "See [the docs](https://docs.example.com/x) or [here](#source-1-2)."
        self.assertEqual(deep_links.sanitize_answer(text), text)
        # A protocol-relative target is not an in-app route either.
        text = "See [elsewhere](//evil.example.com/skills-registry)."
        self.assertEqual(deep_links.sanitize_answer(text), text)

    def test_a_docs_anchor_is_kept_only_when_the_anchor_exists(self) -> None:
        self.assertEqual(
            deep_links.sanitize_answer("Read [Metrics](/docs#metrics)."),
            "Read [Metrics](/docs#metrics).",
        )
        # An anchor that renders nowhere is dropped, and the label does not name a
        # page on its own here, so the link goes with it.
        self.assertEqual(
            deep_links.sanitize_answer("Read [nonsense](/docs#not-a-section)."),
            "Read nonsense.",
        )

    def test_citation_markers_are_not_route_forms(self) -> None:
        text = "Metrics shows your runs [1] and your cost [2, 3]."
        self.assertEqual(deep_links.sanitize_answer(text), text)

    def test_an_admin_route_is_kept_only_for_an_admin(self) -> None:
        # The committed catalogue carries no admin paths, so the rule is pinned
        # against one: an admin-only route is a link for the console's assistant
        # and plain text for everyone else. This also proves the catalogue really
        # is the source — a route it does not list is refused for an admin too.
        with tempfile.TemporaryDirectory() as tmp:
            features = Path(tmp) / "features.json"
            features.write_text(
                json.dumps(
                    {
                        "paths": ["/dashboard", "/admin/users"],
                        "dynamicPrefixes": [],
                        "docAnchors": [],
                        "features": [
                            {"path": "/dashboard", "title": "Dashboard"},
                            {"path": "/admin/users", "title": "Users", "audience": "admin"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ, {"AI_ASSISTANT_FEATURES_JSON": str(features)}
            ):
                deep_links.refresh()
                try:
                    text = "Open [Users](/admin/users) now."
                    self.assertEqual(deep_links.sanitize_answer(text), "Open Users now.")
                    self.assertEqual(
                        deep_links.sanitize_answer(text, allow_admin=True), text
                    )
                finally:
                    deep_links.refresh()


class RouteFilterTests(unittest.TestCase):
    #: The crafted answer: one real link, one invented link, one code span that
    #: holds a route, one ordinary code span, and a citation.
    ANSWER = (
        "Import one in the Skills Registry tab on [Agent skills](/agent-skills) "
        "[1], or from the invented [Skills Registry](/skills-registry) page, "
        "which is not real. Run `pip install x` first, then open `/usage`. [2]"
    )

    def _stream(self, chunks: list[str], *, allow_admin: bool = False) -> str:
        route_filter = deep_links.RouteFilter(allow_admin=allow_admin)
        out = [route_filter.feed(chunk) for chunk in chunks]
        out.append(route_filter.flush())
        return "".join(out)

    def test_streaming_matches_the_whole_text_sanitised(self) -> None:
        expected = deep_links.sanitize_answer(self.ANSWER)
        # Whole answer in one chunk.
        self.assertEqual(self._stream([self.ANSWER]), expected)
        # One character at a time — the worst case for a hold-back bug.
        self.assertEqual(self._stream(list(self.ANSWER)), expected)
        # Ragged chunks that cut through every construct.
        ragged = [self.ANSWER[i : i + 3] for i in range(0, len(self.ANSWER), 3)]
        self.assertEqual(self._stream(ragged), expected)

    def test_an_invented_link_is_never_emitted_even_mid_stream(self) -> None:
        # Incremental output must not leak the dead target at any point: a reader
        # can click while the answer is still arriving.
        route_filter = deep_links.RouteFilter()
        emitted = ""
        for char in "Go to [Skills Registry](/skills-registry) now.":
            emitted += route_filter.feed(char)
            self.assertNotIn("/skills-registry", emitted)
        emitted += route_filter.flush()
        self.assertEqual(emitted, "Go to Skills Registry now.")

    def test_the_tail_is_not_lost_when_a_construct_never_closes(self) -> None:
        # A model can emit an unmatched bracket. The filter holds it back; flush
        # must still deliver it, or the answer would be truncated.
        route_filter = deep_links.RouteFilter()
        emitted = route_filter.feed("Compare [the two options")
        emitted += route_filter.flush()
        self.assertEqual(emitted, "Compare [the two options")

    def test_ordinary_prose_is_emitted_without_delay(self) -> None:
        # Nothing is held when no construct is open — the hold-back must not add
        # latency to a normal answer.
        route_filter = deep_links.RouteFilter()
        self.assertEqual(route_filter.feed("Your runs cost "), "Your runs cost ")
        self.assertEqual(route_filter.feed("$4 this week."), "$4 this week.")


if __name__ == "__main__":
    unittest.main()
