# Computer Use Backend (FastAPI)

A session-based backend API for the Computer Use demo. It manages chat sessions, streams real-time agent events, and persists data in Postgres. It reuses the existing `computer_use_demo` agent loop and tools.

## Quickstart

1) Create a `.env` file in `computer-use-demo/` (not committed to git):

```
ANTHROPIC_API_KEY=your_key_here
DATABASE_URL=postgresql+psycopg://cu:cu@db:5432/cu
# Optional overrides
WIDTH=1366
HEIGHT=768
```

2) Start the backend and Postgres:

```bash
cd computer-use-demo
docker compose -f docker-compose.backend.yml up --build
```

3) Open the test page:

- http://localhost:8080/test
  - Click “New Session” → creates a chat session
  - Type a message and click “Send” → streams events via SSE

## API Endpoints

- POST `/sessions` → Create a new session
- GET `/sessions` → List sessions
- GET `/sessions/{id}` → Get a session
- GET `/sessions/{id}/messages` → List session messages
- POST `/sessions/{id}/messages` → Send a user message; schedules an assistant turn
- GET `/sessions/{id}/events` → SSE stream of `message`, `assistant_chunk`, `http_exchange`

## Deployment

- Backend image: built from `Dockerfile.backend` (backend-only) or `Dockerfile.backend-full` (desktop+backend in one container)
- Database: Postgres 16 managed by docker-compose. Data persisted in `pg_data` volume.

## Notes

- The backend auto-creates tables on startup (SQLAlchemy). For production migrations, add Alembic.
- `.env` is loaded at runtime; Compose also loads it via `env_file`.
- The agent can control the desktop when running the full image; connect to noVNC at `http://localhost:6080/vnc.html`.


