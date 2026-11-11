import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from examples.batch import make_batch_request, make_result_record, read_tickets


class BatchExampleTests(unittest.TestCase):
    def test_reads_csv_and_builds_one_request_per_ticket(self):
        csv_content = (
            "issue_key,summary,description,acceptance_criteria\n"
            "DEMO-1,Login issue,Users cannot sign in,Login succeeds with valid credentials\n"
            "DEMO-2,Slow page,Dashboard is slow,\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "tickets.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
                csv_file.write(csv_content)

            tickets = read_tickets(csv_path)
            requests = [make_batch_request(ticket, "test-model") for ticket in tickets]

        self.assertEqual(len(requests), 2)
        self.assertEqual([request["custom_id"] for request in requests], ["DEMO-1", "DEMO-2"])
        self.assertEqual(requests[0]["params"]["model"], "test-model")
        self.assertEqual(requests[0]["params"]["max_tokens"], 2048)
        prompt = requests[0]["params"]["messages"][0]["content"]
        self.assertIn("acceptance criteria", prompt)
        self.assertIn("at most five ambiguities", prompt)

    def test_rejects_csv_without_required_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "tickets.csv"
            csv_path.write_text("summary\nMissing key\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "issue_key"):
                read_tickets(csv_path)

    def test_rejects_duplicate_issue_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "tickets.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["issue_key", "summary"])
                writer.writerow(["DEMO-1", "First ticket"])
                writer.writerow(["DEMO-1", "Duplicate ticket"])

            with self.assertRaisesRegex(ValueError, "Duplicate issue_key"):
                read_tickets(csv_path)

    def test_parses_valid_analysis_json(self):
        result = SimpleNamespace(
            type="succeeded",
            message=SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"readiness":{"status":"ready"}}')],
                stop_reason="end_turn",
            ),
        )

        record = make_result_record("DEMO-1", result)

        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["analysis"], {"readiness": {"status": "ready"}})

    def test_records_invalid_json_and_continues(self):
        malformed_response = '{"readiness":{"rationale":"truncated'
        result = SimpleNamespace(
            type="succeeded",
            message=SimpleNamespace(
                content=[SimpleNamespace(type="text", text=malformed_response)],
                stop_reason="max_tokens",
            ),
        )

        record = make_result_record("DEMO-2", result)

        self.assertEqual(record["status"], "invalid_analysis_json")
        self.assertEqual(record["raw_response"], malformed_response)
        self.assertEqual(record["error"]["stop_reason"], "max_tokens")


if __name__ == "__main__":
    unittest.main()
