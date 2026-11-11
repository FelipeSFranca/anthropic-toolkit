# Anthropic API Examples

A collection of practical Python examples exploring the Anthropic SDK capabilities.

## Setup

Use Git Bash for the commands in this README. From the project directory, create
and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root:

```dotenv
ANTHROPIC_API_KEY=your-api-key
ANTHROPIC_MODEL=your-model-id
```

The examples load `.env` automatically. `.env` is ignored by Git; do not commit
API keys.

## Examples

### Minimal Messages API request

Send a minimal Messages API request:

```bash
python examples/hello.py
```

### Ticket Quality Analyzer (Messages Batches API)

The batch example reads a Jira CSV and submits one analysis request per ticket.
It evaluates clarity, acceptance criteria, ambiguity, and readiness for
development. The CSV must include `issue_key` and `summary`; description and
acceptance criteria are used when present.

Submit the included sample CSV:

```bash
python examples/batch.py submit examples/jira_tickets_sample.csv
```

Submission saves the batch ID in `examples/.batch_id`. Batch processing is
asynchronous, so retrieve the results later:

```bash
python examples/batch.py retrieve
```

If processing has not ended, the command prints the current counts; run it
again later. Once complete, results are written to
`ticket_quality_results.jsonl`, with one JSON object per ticket. Each line
contains the ticket's `issue_key`, result `status`, and either the analysis or
an error.

You can provide a different CSV, batch ID, or output path:

```bash
python examples/batch.py submit path/to/tickets.csv
python examples/batch.py retrieve --batch-id msgbatch_...
python examples/batch.py retrieve --output results.jsonl
```

### HTML Quality Report

Generate a self-contained HTML report from the batch JSONL results. The script
validates successful analyses, skips and counts invalid analysis records,
calculates aggregate metrics, asks Claude for up to three structured insights,
and saves the report to
`examples/ticket_quality_report.html`.

```bash
python examples/report.py
```

By default, it reads `examples/ticket_quality_results.jsonl`. Choose different
input, output, or model values with:

```bash
python examples/report.py --input path/to/results.jsonl --output report.html
python examples/report.py --model your-model-id
```

The configured Claude model must support Anthropic structured JSON outputs.
The HTML layout and inline CSS are in
`examples/templates/report.html`; charts are rendered locally, with no external
assets or charting dependencies. Recommendations use aggregate metrics and up
to six selected ticket examples; Claude does not analyze the full text of every
ticket in the batch.

## Tests

Run the local tests without making API calls:

```bash
python -m unittest discover -s tests -v
```
