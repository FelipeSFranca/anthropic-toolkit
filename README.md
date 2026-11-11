# Anthropic API Examples

A collection of practical Python examples exploring the Anthropic SDK capabilities.

## Setup

From the project directory, create a virtual environment and install the
dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

In Git Bash, activate the environment with:

```bash
source .venv/Scripts/activate
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

```powershell
python examples\hello.py
```
