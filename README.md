# factored-hackathon-2026-epsilon-greedy

AI-first **transaction-dispute intake** agent for a LATAM bank (Spanish and Portuguese), built for the Factored AI & Data Hackathon 2026.

> The LLM understands and writes. Deterministic code decides, acts and verifies.


## Quick start

## Repository structure

```
.
├── data/                   # Input data (not versioned, see "Data")
├── docs/
│   ├── policies.md         # Policies / business rules used in the analysis
│   └── findings_tables.txt # Tables with the profiling findings
├── profiling.ipynb         # Main data profiling notebook
├── pyproject.toml          # Project dependencies
├── uv.lock                 # Exact dependency versions
└── .python-version         # Project Python version
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python environment and dependency manager)
- Git
To install uv on macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

You don't need to install Python separately. uv downloads the version specified in `.python-version`.

## Setup

```bash
git clone <repo-URL>
cd <repo-name>
uv sync
```

`uv sync` creates the virtual environment in `.venv/` and installs the exact versions pinned in `uv.lock`.

## Data

The `data/` folder is not committed to the repository. To run the analysis:

1. Create the folder if it doesn't exist: `mkdir -p data`
2. Place the input files there:
   <!-- TODO: list the expected files, for example:
   - `data/source_file.csv`: description
   -->
3. <!-- TODO: explain where to get them (shared drive, database, etc.) -->

## Documentation

- **`docs/policies.md`**: rules and criteria used in the analysis. <!-- TODO: adjust description -->
- **`docs/findings_tables.txt`**: tables with the profiling findings.



## Submission checklist (due Oct 5 to hackathon.admin@factored.ai)

- [ ] Deployed link
- [ ] 4–6 slide presentation
- [ ] Video pitch: working demo + core architecture decisions
- [ ] Demo cases in ES and PT: normal resolution, ambiguous/unsupported, human-required


