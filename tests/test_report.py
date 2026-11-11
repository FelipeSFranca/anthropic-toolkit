import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from examples.report import (
    calculate_metrics,
    generate_insights,
    load_results,
    main,
    render_html_report,
    select_sample_findings,
)


def make_analysis(
    score=3,
    acceptance_status="partial",
    readiness_status="needs_clarification",
):
    return {
        "clarity": {"score": score, "assessment": "Some details need clarification."},
        "acceptance_criteria": {
            "status": acceptance_status,
            "assessment": "Some criteria are incomplete.",
        },
        "ambiguities": ["The intended behavior is not specified."],
        "readiness": {
            "status": readiness_status,
            "rationale": "Clarify the expected behavior before implementation.",
            "questions": ["What behavior should be expected?"],
        },
    }


def make_record(issue_key, analysis=None, status="succeeded"):
    record = {"issue_key": issue_key, "status": status}
    if analysis is not None:
        record["analysis"] = analysis
    return record


class ReportTests(unittest.TestCase):
    def test_loads_and_validates_successful_results_and_counts_other_statuses(self):
        records = [
            make_record("DEMO-1", make_analysis(score=4, acceptance_status="missing")),
            make_record("DEMO-2", make_analysis(score=2, readiness_status="not_ready")),
            make_record("DEMO-3", status="errored"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "results.jsonl"
            input_path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            analyses, statuses = load_results(input_path)

        metrics = calculate_metrics(analyses, statuses)
        self.assertEqual(metrics["total_tickets"], 3)
        self.assertEqual(metrics["valid_analyses"], 2)
        self.assertEqual(metrics["other_results"], 1)
        self.assertEqual(metrics["average_clarity"], 3)
        self.assertNotIn("missing_acceptance_percentage", metrics)
        self.assertEqual(metrics["readiness_counts"]["not_ready"], 1)

    def test_skips_invalid_successful_analysis_and_counts_it_once(self):
        records = [
            make_record("DEMO-1", make_analysis(score=6)),
            make_record("DEMO-2", make_analysis(score=4)),
            make_record("DEMO-3", status="errored"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "results.jsonl"
            input_path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                analyses, statuses = load_results(input_path)

        self.assertEqual([item["issue_key"] for item in analyses], ["DEMO-2"])
        self.assertEqual(statuses["succeeded"], 1)
        self.assertEqual(statuses["invalid_analysis"], 1)
        self.assertEqual(statuses["errored"], 1)
        metrics = calculate_metrics(analyses, statuses)
        self.assertEqual(metrics["total_tickets"], 3)
        self.assertEqual(metrics["other_results"], 2)
        self.assertIn("Skipping invalid analysis", stderr.getvalue())

    def test_selects_two_compact_findings_per_readiness_category(self):
        analyses = [
            {
                "issue_key": f"DEMO-{index}",
                "analysis": make_analysis(
                    score=index,
                    acceptance_status="missing" if index == 1 else "sufficient",
                    readiness_status=(
                        "not_ready"
                        if index < 3
                        else "needs_clarification"
                        if index < 5
                        else "ready"
                    ),
                ),
            }
            for index in range(1, 7)
        ]

        analyses[0]["analysis"]["readiness"]["rationale"] = "Long rationale " * 40
        findings = select_sample_findings(analyses)

        self.assertEqual(len(findings), 6)
        self.assertEqual(
            [finding["readiness_status"] for finding in findings],
            [
                "not_ready",
                "not_ready",
                "needs_clarification",
                "needs_clarification",
                "ready",
                "ready",
            ],
        )
        self.assertLessEqual(len(findings[0]["rationale"]), 220)
        self.assertNotIn("analysis", findings[0])

    def test_generates_structured_insights_through_sdk(self):
        insight_data = {
            "insights": [
                {
                    "title": "Clarify requirements",
                    "finding": "Several tickets are not ready.",
                    "recommendation": "Add testable acceptance criteria.",
                    "supporting_tickets": ["DEMO-1"],
                }
            ]
        }

        class FakeMessages:
            def create(self, **kwargs):
                self.request = kwargs
                return SimpleNamespace(
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=123, output_tokens=45),
                    content=[
                        SimpleNamespace(
                            type="text", text=json.dumps(insight_data)
                        )
                    ],
                )

        fake_messages = FakeMessages()
        client = SimpleNamespace(messages=fake_messages)
        stdout = StringIO()
        with redirect_stdout(stdout):
            insights = generate_insights(
                client,
                "test-model",
                {"valid_analyses": 1},
                [{"issue_key": "DEMO-1", "readiness_status": "not_ready"}],
            )

        self.assertEqual(insights, insight_data["insights"])
        self.assertIn("Input tokens: 123", stdout.getvalue())
        self.assertIn("Output tokens: 45", stdout.getvalue())
        self.assertEqual(
            fake_messages.request["output_config"]["format"]["type"], "json_schema"
        )
        prompt = fake_messages.request["messages"][0]["content"]
        self.assertIn("sample findings", prompt)
        self.assertNotIn("representative findings", prompt)
        self.assertIn('"sample_findings":', prompt)
        self.assertNotIn('"representative_findings":', prompt)
        self.assertEqual(
            fake_messages.request["output_config"]["format"]["schema"]["properties"]
            ["insights"]["items"]["type"],
            "object",
        )
        self.assertNotIn(
            "maxItems",
            fake_messages.request["output_config"]["format"]["schema"]["properties"]
            ["insights"],
        )
        self.assertIn(
            "supporting_tickets",
            fake_messages.request["output_config"]["format"]["schema"]["properties"]
            ["insights"]["items"]["required"],
        )

    def test_rejects_non_end_turn_stop_reason(self):
        class FakeMessages:
            def create(self, **kwargs):
                return SimpleNamespace(
                    stop_reason="max_tokens",
                    usage=SimpleNamespace(input_tokens=20, output_tokens=10),
                    content=[],
                )

        client = SimpleNamespace(messages=FakeMessages())
        with redirect_stdout(StringIO()):
            with self.assertRaisesRegex(
                ValueError, "Unexpected Claude stop reason: max_tokens"
            ):
                generate_insights(
                    client,
                    "test-model",
                    {},
                    [{"issue_key": "DEMO-1", "readiness_status": "ready"}],
                )

    def test_accepts_missing_unused_assessment_fields(self):
        analysis = make_analysis()
        del analysis["clarity"]["assessment"]
        del analysis["acceptance_criteria"]["assessment"]
        del analysis["readiness"]["questions"]
        record = make_record("DEMO-1", analysis)

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "results.jsonl"
            input_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            analyses, statuses = load_results(input_path)

        self.assertEqual(len(analyses), 1)
        self.assertEqual(statuses["succeeded"], 1)

    def test_rejects_insight_citing_unprovided_ticket(self):
        response_data = {
            "insights": [
                {
                    "title": "Title",
                    "finding": "Finding",
                    "recommendation": "Recommendation",
                    "supporting_tickets": ["DEMO-404"],
                }
            ]
        }

        class FakeMessages:
            def create(self, **kwargs):
                return SimpleNamespace(
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=20, output_tokens=10),
                    content=[
                        SimpleNamespace(type="text", text=json.dumps(response_data))
                    ],
                )

        client = SimpleNamespace(messages=FakeMessages())
        with self.assertRaisesRegex(ValueError, "unknown tickets: DEMO-404"):
            generate_insights(
                client,
                "test-model",
                {},
                [{"issue_key": "DEMO-1", "readiness_status": "ready"}],
            )

    def test_renders_self_contained_html_and_escapes_insights(self):
        metrics = calculate_metrics(
            [{"issue_key": "DEMO-1", "analysis": make_analysis()}],
            {"succeeded": 1},
        )
        html_report = render_html_report(
            metrics,
            [
                {
                    "title": "<script>alert(1)</script>",
                    "finding": "Finding",
                    "recommendation": "Recommendation",
                    "supporting_tickets": ["DEMO-1"],
                }
            ],
            "results.jsonl",
        )

        self.assertIn("<!doctype html>", html_report)
        self.assertIn("Development readiness", html_report)
        self.assertIn("DEMO-1", html_report)
        self.assertIn("Supporting tickets", html_report)
        self.assertIn("Excluded or unsuccessful analyses", html_report)
        self.assertIn("&lt;script&gt;", html_report)
        self.assertNotIn("<script>alert(1)</script>", html_report)
        self.assertNotIn("https://", html_report)

    def test_substitutes_template_metrics_without_unresolved_placeholders(self):
        metrics = calculate_metrics(
            [
                {
                    "issue_key": "DEMO-1",
                    "analysis": make_analysis(
                        score=4,
                        acceptance_status="missing",
                        readiness_status="ready",
                    ),
                }
            ],
            {"succeeded": 1},
        )

        html_report = render_html_report(metrics, [], "results<&>.jsonl")

        self.assertIn('<div class="badge">1 tickets</div>', html_report)
        self.assertIn("Average clarity</span><strong class=\"metric-value\">4.0 / 5", html_report)
        self.assertIn("Ready for development</span><strong class=\"metric-value\">100.0%", html_report)
        self.assertIn("Missing acceptance criteria</span><strong class=\"metric-value\">1", html_report)
        self.assertIn("Source: results&lt;&amp;&gt;.jsonl", html_report)
        self.assertNotRegex(html_report, r"\$[a-zA-Z_][a-zA-Z0-9_]*")

    def test_main_creates_custom_output_parent_directory(self):
        record = make_record("DEMO-1", make_analysis())
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "results.jsonl"
            input_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            output_path = Path(temp_dir) / "nested" / "report.html"

            with patch.object(
                sys,
                "argv",
                [
                    "report.py",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--model",
                    "test-model",
                ],
            ):
                with patch("examples.report.Anthropic"):
                    with patch("examples.report.generate_insights", return_value=[]):
                        main()

            self.assertTrue(output_path.is_file())
            self.assertIn("Jira Ticket Quality Report", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
