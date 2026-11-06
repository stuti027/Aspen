# Aspen
### AI-Powered Website Testing Platform

Aspen is an AI-powered website testing platform that analyzes websites, identifies functionality and UI/UX issues, and generates structured testing results with supporting evidence.

It combines browser automation, AI-powered test generation, multi-agent execution, and responsive UI analysis to evaluate website quality.

## Development Progress

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Backend Infrastructure | Complete |
| Phase 2 | Browser & Test Execution Infrastructure | Complete |
| Phase 3 | Functionality Agent | Complete |
| Phase 4 | UI/UX Agent | Complete |
| Phase 5 | Time Simulation Agent | Complete |
| Phase 6 | Orchestration Agent | Complete |
| Phase 7 | Report Agent | Upcoming |
| Phase 8 | Frontend | Upcoming |

## Tech Stack

- **Backend:** Python, FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Migrations:** Alembic
- **Validation:** Pydantic
- **Authentication:** JWT, bcrypt
- **Browser Automation:** Chrome DevTools Protocol (CDP)
- **AI Integration:** Google Gemini API, LangChain
- **Containerization:** Docker Compose

## Implemented Agents

### 1. Functionality Agent

Executes website testing workflows using browser automation and AI-generated test plans.

**Supported actions:**
- Navigate
- Click
- Fill
- Screenshot

**AI capabilities:**
- Generates test workflows based on a testing objective and page context.
- Executes generated workflows through browser automation.
- Analyzes failed test steps to identify likely causes.
- Provides explanations and recommendations for detected failures.

### 2. UI/UX Agent

Analyzes websites across desktop, tablet, and mobile viewports using deterministic browser scans and AI-powered UX exploration.

**Capabilities:**

- **UI Analysis:** Page structure, headings, landmarks, and layout.
- **Visual Analysis:** Missing alt text, broken images, small text, and basic contrast checks.
- **Responsiveness:** Horizontal overflow and viewport boundary detection.
- **Accessibility:** Form labels, accessible names, and heading hierarchy.
- **Usability:** Placeholder links, small interactive targets, and disabled controls.
- **AI-Powered Exploration:** Interacts with website elements to evaluate navigation, clarity, and user friction.
- **UX Evaluation:** Generates consolidated findings, strengths, and recommendations.

**Viewports tested:**

| Device | Resolution |
|---|---|
| Desktop | 1440 × 900 |
| Tablet | 768 × 1024 |
| Mobile | 390 × 844 |

The agent generates severity-classified findings and screenshots for each viewport.

### 3. Time Simulation Agent

Simulates the passage of time during website testing using browser clock manipulation.

**Capabilities:**
- Installs a simulated browser clock.
- Advances time by a specified number of milliseconds.
- Retrieves the current simulated timestamp.
- Supports testing of time-dependent website functionality.

### 4. Orchestration Agent

Coordinates multiple testing agents through a unified execution workflow.

**Capabilities:**
- Creates test plans based on selected agents and testing inputs.
- Executes agents in a defined order.
- Supports AI-generated and user-defined functionality workflows.
- Integrates time simulation with functionality testing.
- Maintains shared context containing completed agent results.
- Handles execution failures and retries.
- Preserves structured failure analysis in the final execution response.

## Shared AI Service

Aspen uses a shared Gemini LLM service through LangChain.

**Capabilities:**
- Text generation.
- Structured output generation using Pydantic schemas.
- Multimodal requests with screenshots.
- Request timeouts and retry handling.
- Exponential backoff for retryable failures.
- Graceful handling of quota exhaustion and temporary service unavailability.

The shared service provides consistent LLM integration and error handling across the implemented agents.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/api/auth/register` | POST | User registration |
| `/api/auth/login` | POST | User authentication |
| `/api/tests/run-custom-test` | POST | Functionality testing |
| `/api/tests/run-uiux-test` | POST | UI/UX analysis |

Swagger documentation: `http://127.0.0.1:8000/docs`

## Testing and Verification

The implemented agents and orchestration workflow have been tested using real browser execution and Gemini integration.

**Integration testing covered:**
- Gemini-generated functionality test plans.
- Browser navigation, clicking, and screenshot capture.
- UI/UX analysis across all three viewport configurations.
- AI-powered website exploration and evaluation.
- Simulated time advancement.
- Multi-agent execution through orchestration.
- Failure detection and AI-generated failure diagnosis.
- Propagation of structured failure analysis through orchestration.
- Gemini retry and fallback behaviour.

### UI/UX Agent Testing

Testing was conducted using:
- A controlled HTML page containing deliberately introduced UI/UX issues.
- Wikipedia (`https://www.wikipedia.org/`).

**Controlled test results:**

| Metric | Count |
|---|---:|
| Total findings | 13 |
| High | 2 |
| Medium | 7 |
| Low | 4 |

Testing covered all three viewport configurations. Screenshot generation and browser cleanup were also verified.

## Setup and Execution

### 1. Clone the repository

```bash
git clone <repository-url>
cd Aspen
```

### 2. Start the database

```bash
docker compose up -d db
```

### 3. Set up the Python environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Configure environment variables

Create a `.env` file using `.env.example` and configure the required application settings.

Set the Gemini API key as a process environment variable in PowerShell:

```powershell
$env:GEMINI_API_KEY="YOUR_API_KEY"
```

The API key should never be committed to the repository or included in distributable project files.

### 6. Apply database migrations

```powershell
alembic upgrade head
```

### 7. Start the backend

```powershell
uvicorn app.main:app --reload
```

**Backend:** `http://127.0.0.1:8000`

**Swagger:** `http://127.0.0.1:8000/docs`


**Current Status: Phases 1–6 complete. Report Agent and frontend development are upcoming.**