# DataLens

DataLens is a FastAPI-based data audit workspace for exploring decision datasets before they are used in analytics, automation, or model workflows. It helps teams upload tabular data, review column behavior, detect sensitive or proxy attributes, check fairness signals, inspect dataset readiness, and export practical audit artifacts.

The project is still under active development, so the current focus is local use, iteration, and source control. Deployment files will be added once the app is ready for production hosting.

## What It Does

- Upload CSV or Excel datasets through a browser interface
- Profile columns with data types, null rates, unique counts, and plain-language descriptions
- Detect sensitive attributes and proxy columns with model-assisted checks and deterministic fallbacks
- Run fairness metrics such as demographic parity, disparate impact ratio, and statistical significance checks
- Estimate feature influence and counterfactual decision sensitivity
- Map potential EU AI Act-style risk indicators for review
- Apply a reweighing-based correction workflow for selected audit columns
- Generate downloadable CSV, PDF, Excel, and JSON outputs
- Keep local audit history separated by browser session

## Tech Stack

- Python
- FastAPI
- Pandas and NumPy
- SciPy and scikit-learn
- ReportLab and OpenPyXL
- HTML, CSS, and browser JavaScript
- Optional Gemini and Groq integrations

## Project Structure

```text
frontend/      Static browser interface
routes/        FastAPI endpoints
services/      Dataset, fairness, export, security, and audit logic
data/uploads/  Local uploaded datasets, ignored by Git
data/reports/  Local generated reports, ignored by Git
```

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a local environment file:

```powershell
copy .env.example .env
```

Add optional API keys in `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
FILE_ENCRYPTION_KEY=generate_a_fernet_key_for_persistent_encryption
ENABLE_HTTPS_REDIRECT=false
```

The app can still run without model API keys by using local fallback logic.

## Run Locally

```powershell
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Notes

Local uploads, generated reports, SQLite database files, logs, virtual environments, and `.env` secrets are ignored by Git. Do not commit real API keys or private datasets.
