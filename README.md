# Chrono Assist API

> A multi-tenant productivity backend that brings together secure team management, document intelligence, email workflows, task management, and AI-assisted Google Calendar operations.

Built with Django REST Framework, PostgreSQL + pgvector, MinIO, Ollama, and Google Calendar.

## Highlights

- **Secure access** — email/password authentication with a two-step email OTP login flow, session support, and optional JWT endpoints.
- **Team workspaces** — a main user represents a company workspace; sub-users belong to that workspace and receive scoped roles.
- **Role-based access control** — feature/action permissions control user management, files, prompts, calendar actions, mail, and tasks.
- **Private document hub** — upload and preview company files stored in MinIO-compatible object storage.
- **Document RAG** — extract text from PDF, DOCX, PPTX, and TXT files; chunk and embed content with Ollama; search vectors through pgvector; then chat with either all workspace documents or one document.
- **AI calendar assistant** — connect Google Calendar through OAuth 2.0, manage events through the API, or use natural-language commands parsed by a local Llama model.
- **Productivity modules** — dedicated mail, calendar, task, document, authentication, and RBAC apps.

## Architecture

```text
Client application
      │
      ▼
Django REST Framework API
├── authapp       Authentication, OTP, profiles, team members
├── rbac          Roles and feature/action permissions
├── file_upload   MinIO documents, embeddings, RAG chat
├── calendar_app  Google Calendar OAuth, CRUD, AI commands
├── mail          Email workflows
└── tasks         Task management
      │
      ├── PostgreSQL + pgvector  → application data and embeddings
      ├── MinIO                  → profile images and uploaded files
      ├── Ollama                 → embeddings and local LLM inference
      ├── SMTP                   → OTP email delivery
      └── Google Calendar API    → calendar integration
```

## Tech Stack

| Area | Technology |
| --- | --- |
| Backend | Python, Django, Django REST Framework |
| Database | PostgreSQL with pgvector |
| Object storage | MinIO via `django-storages` / S3-compatible APIs |
| AI / RAG | Ollama, LangChain text splitters, Llama 3.2, `all-minilm:l6-v2` embeddings |
| Authentication | Django sessions, email OTP, Simple JWT |
| Calendar | Google OAuth 2.0 and Google Calendar API |
| Deployment tooling | Docker Compose (MinIO service) |

## Quick Start

### Prerequisites

Install and make available:

- Python 3.11+ and `pip`
- PostgreSQL with the **pgvector** extension enabled
- Docker and Docker Compose
- [Ollama](https://ollama.com/) for local inference and embeddings
- A Google Cloud OAuth client if you will use Calendar features
- SMTP credentials if you will use OTP email delivery

### 1. Clone and set up Python

```bash
git clone <your-repository-url>
cd backend

python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Start MinIO

The included Compose configuration starts MinIO on port `9000` and its console on port `9001`.

```bash
docker compose up -d
```

Open the console at [http://localhost:9001](http://localhost:9001), sign in with the credentials configured in `docker-compose.yml`, and create the bucket named by `MINIO_BUCKET_NAME`.

### 3. Start Ollama models

```bash
ollama pull llama3.2:3b
ollama pull all-minilm:l6-v2
```

> The project uses `llama3.2:3b` to turn calendar language into structured commands and `all-minilm:l6-v2` to generate document embeddings.

### 4. Configure environment variables

Create a `.env` file inside `backend/`:

```env
# Django
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000

# PostgreSQL
DB_NAME=chrono
DB_USER=postgres
DB_PASSWORD=your-postgres-password
DB_HOST=127.0.0.1
DB_PORT=5432

# MinIO / S3-compatible storage
MINIO_ENDPOINT_URL=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET_NAME=chrono-assist
MINIO_REGION=us-east-1

# SMTP / OTP email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-email-app-password

# Google Calendar OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/calendar/google/callback/

# Ollama (optional when using the default local endpoint)
OLLAMA_HOST=http://localhost:11434
```

For Google Calendar, register the same redirect URI in the Google Cloud Console. Never commit `.env` files, OAuth secrets, SMTP passwords, database passwords, or MinIO credentials.

### 5. Prepare the database and run

```bash
python manage.py migrate
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/`.

## API Map

All paths below are relative to the API host.

| Area | Base path | Main operations |
| --- | --- | --- |
| Authentication | `/authapp/` | CSRF, registration, OTP login, profiles, sub-users, permissions |
| Documents & RAG | `/file_upload/` | Upload, list, delete, embed, preview, workspace/document chat |
| Roles | `/rbac/` | Role and role-permission management |
| Mail | `/api/mail/` | Mail features |
| Calendar | `/api/calendar/` | Google OAuth, event CRUD, AI calendar prompt |
| Tasks | `/api/tasks/` | Task management |
| JWT | `/api/token/` | Access and refresh token endpoints |

### Authentication flow

1. Request `GET /authapp/csrf/` from browser clients to receive the CSRF cookie.
2. Register an owner with `POST /authapp/register/`.
3. Log in using `POST /authapp/login/` with `email` and `password`.
4. Enter the emailed code at `POST /authapp/verify-otp/` with `email` and `code`.
5. Query `GET /authapp/my-permissions/` to drive permission-aware UI behavior.

```bash
# Start login: sends the OTP after verifying credentials
curl -X POST http://127.0.0.1:8000/authapp/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"your-password"}'

# Verify the OTP and create the session
curl -X POST http://127.0.0.1:8000/authapp/verify-otp/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","code":"123456"}'
```

### Document RAG flow

1. Upload a document through `POST /file_upload/uploadfile/` using multipart form data.
2. Send its UUID to `POST /file_upload/embedfile/` to extract, chunk, and embed its text.
3. Ask questions across the workspace with `POST /file_upload/ragchat/`, or against a specific embedded file with `POST /file_upload/docchat/`.
4. Request `GET /file_upload/previewfile/<document_id>/` for a temporary MinIO preview URL.

Supported extraction formats: PDF, DOCX, PPTX, and text files.

### Calendar AI example

First connect a Google account with `GET /api/calendar/google/login/`. Then a permitted user can send a natural-language prompt:

```json
POST /api/calendar/ai-prompt/
{
  "prompt": "Schedule a project planning meeting tomorrow at 3 PM for one hour"
}
```

The calendar service parses the instruction into a validated create, list, update, or delete action before calling the Google Calendar API.

## Workspace and RBAC model

Chrono Assist isolates data by workspace:

- A self-registered **main** user becomes the workspace owner.
- Registration clones the default `Owner` role template for that workspace.
- Main users can create **sub** users and assign workspace-scoped roles.
- Permissions use feature/action pairs such as `files:view`, `files:create`, `calendar:execute`, or `prompt:execute`.
- Documents, roles, and user-management operations are scoped to the current workspace to prevent cross-company access.

## Project Structure

```text
backend/
├── backend/           # Django settings and root routing
├── authapp/           # Custom user model, email OTP auth, profiles
├── rbac/              # Roles, permissions, permission checks
├── file_upload/       # MinIO files, pgvector embeddings, RAG endpoints
├── calendar_app/      # Google Calendar and AI command processing
├── mail/              # Mail domain features
├── tasks/             # Task domain features
├── docker-compose.yml # Local MinIO service
├── requirements.txt
└── manage.py
```

## Security Notes

- Use `DEBUG=False`, a strong `SECRET_KEY`, HTTPS, restricted `ALLOWED_HOSTS`, and production CORS origins outside local development.
- Restrict MinIO bucket policies and rotate its access credentials before deployment.
- Use an SMTP app password rather than an account password.
- Google OAuth credentials are currently stored centrally by the calendar module. For a multi-user production deployment, associate credentials with a user/workspace and encrypt tokens at rest.
- Keep the LLM and embedding services on trusted infrastructure; uploaded documents may be sent to the configured Ollama service for processing.

## Development

```bash
# Create migrations after model changes
python manage.py makemigrations
python manage.py migrate

# Run the test suite
python manage.py test

# Create an admin user (optional)
python manage.py createsuperuser
```

## Roadmap

- Add automated unit and integration coverage for authentication, RBAC, RAG, and Calendar flows.
- Move Google credentials to encrypted, per-user/workspace storage.
- Add production-ready service orchestration for PostgreSQL/pgvector, Ollama, Django, and MinIO.
- Add API schema documentation and example client collections.

## License

Add a `LICENSE` file to define the terms under which this project can be used, modified, and distributed.
