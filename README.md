# terminaide

A Python package for serving CLI applications in the browser using ttyd.

## Installation

```bash
pip install terminaide
```

## Usage

```python
from fastapi import FastAPI
from terminaide import serve_tty

app = FastAPI()

serve_tty(app, client_script="path/to/your/script.py")
```

## Development

```bash
# Install dependencies
poetry install

# Run test server
poetry run python test-server/main.py
```