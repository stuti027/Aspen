# Aspen
### AI-Powered Website Testing Platform

Aspen is an AI-powered website testing platform that analyzes websites, identifies functionality and UI/UX issues, and generates structured testing results with supporting evidence.

## Development Progress

| Phase | Status |
|---|---|
| Phase 1 | Complete |
| Phase 2 | Complete |
| Phase 3 | Complete |
| Phase 4: UIUX Agent | Complete |
| Phase 5–8 | Upcoming |

## Tech Stack

- **Backend:** Python, FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Migrations:** Alembic
- **Validation:** Pydantic
- **Authentication:** JWT, bcrypt
- **Browser Automation:** Chrome DevTools Protocol (CDP)
- **Containerization:** Docker Compose

## Implemented Agents

### 1. Functionality Agent
Executes custom website testing workflows using browser automation.

Supported actions:
- Navigate
- Click
- Fill
- Screenshot

### 2. UIUX Agent
Analyzes websites across desktop, tablet and mobile viewports.

Capabilities:
- **UI Analysis:** Page structure, headings and landmarks.
- **Visual Analysis:** Missing alt text, broken images, small text and basic contrast checks.
- **Responsiveness:** Horizontal overflow and viewport boundary detection.
- **Accessibility:** Form labels, accessible names and heading hierarchy.
- **Usability:** Placeholder links, small interactive targets and disabled controls.

**Viewports tested:**

| Device | Resolution |
|---|---|
| Desktop | 1440 × 900 |
| Tablet | 768 × 1024 |
| Mobile | 390 × 844 |

The agent generates severity-classified findings and screenshots for each viewport.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/api/auth/register` | POST | User registration |
| `/api/auth/login` | POST | User authentication |
| `/api/tests/run-custom-test` | POST | Functionality testing |
| `/api/tests/run-uiux-test` | POST | UIUX analysis |

Swagger documentation: `http://127.0.0.1:8000/docs`

## UIUX Agent Testing

Tested using:
- A controlled HTML page containing deliberately introduced UI/UX issues.
- Wikipedia (`https://www.wikipedia.org/`).

Controlled test results:

| Metric | Count |
|---|---:|
| Total findings | 13 |
| High | 2 |
| Medium | 7 |
| Low | 4 |

Testing covered all three viewport configurations. Screenshot generation and browser cleanup were also verified.

## Setup and Execution

**1. Clone the repository**

```bash
git clone <repository-url>
cd Aspen
```

**2. Start the database**

```bash
docker compose up -d db
```

**3. Set up the Python environment**

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**4. Install dependencies**

```bash
pip install -r requirements.txt
```

**5. Configure environment variables**

Create a `.env` file using `.env.example`.

**6. Apply database migrations**

```bash
alembic upgrade head
```

**7. Start the backend**

```bash
uvicorn app.main:app --reload
```

Backend: `http://127.0.0.1:8000`

Swagger: `http://127.0.0.1:8000/docs`

---

**Current Status:** Phases 1, 2, 3 and 4 completed. Development continues with Phase 5.