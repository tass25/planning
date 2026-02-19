# SAS Converter

A partition-based SAS-to-Python conversion pipeline using multi-agent architecture.

## Setup

```bash
# Activate virtual environment
.\venv\Scripts\Activate.ps1  # Windows

# Install dependencies
pip install -r sas_converter/requirements.txt
```

## Project Structure

```
sas_converter/
├── partition/
│   ├── base_agent.py          # BaseAgent ABC
│   ├── logging_config.py      # structlog configuration
│   ├── models/                # Pydantic data models
│   ├── entry/                 # L2-A agents (FileAnalysis, CrossFileDeps, RegistryWriter)
│   └── db/                    # SQLAlchemy database management
├── tests/                     # pytest test suite
├── knowledge_base/
│   └── gold_standard/         # 50 annotated .sas + .gold.json files
├── config/
│   └── project_config.yaml    # Project configuration
└── requirements.txt
```

## Running Tests

```bash
pytest sas_converter/tests/ -v --cov=sas_converter.partition
```
