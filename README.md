# Nwoma

**Clinical paperwork, made structured.**

Nwoma (Asante Twi: paper, document) turns messy clinical documents, PDFs or scans in English or
French, into structured, coded and verified records, with a human reviewing anything uncertain.

> Status: early development. Results will be published here once the evaluation report exists.

- Why it is built this way: [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md)
- Decisions: [`docs/adr/`](docs/adr/)

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy .
```

## Data

Nwoma is developed on **synthetic data only**. No real patient information is used anywhere.

## Licence

MIT
