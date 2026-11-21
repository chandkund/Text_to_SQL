# Pagila Text-to-SQL Assistant

This project lets users ask questions about the Pagila DVD rental database in plain English. A Next.js chat interface sends questions to a FastAPI backend, which asks Gemini to generate PostgreSQL, validates the query, and runs it against a read-only Neon Postgres database. The answer includes an explanation, SQL, and query results.

**Live demo:** [Open the app](https://your-demo-url.vercel.app) *(replace this placeholder with the deployed Vercel URL)*

## Tech stack

- **Frontend:** Next.js App Router, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Python
- **LLM:** Gemini (`gemini-3.8-flash`)
- **SQL validation:** sqlglot (PostgreSQL dialect)
- **Database:** Neon Postgres with the Pagila dataset
- **Deployment:** Vercel (frontend), Render (backend)

## Architecture

```text
User
  |
  v
Next.js chat UI
  |
  | POST /ask { question }
  v
FastAPI backend
  |
  v
Gemini generates SQL and explanation
  |
  v
sqlglot validates the SQL
  |
  v
Neon Postgres (Pagila, read-only user)
  |
  v
FastAPI returns explanation, SQL, columns, and rows
  |
  v
Next.js displays the answer
```

At startup, the backend reads the allowed tables and columns from `information_schema` and includes that schema and join guidance in the Gemini prompt.

## Query safety

- **SELECT-only validation:** sqlglot parses the generated PostgreSQL and the backend accepts exactly one `SELECT` statement. It rejects other statement types and tables outside the approved Pagila table list.
- **Result limit:** if a query has no `LIMIT`, the backend adds `LIMIT 100`.
- **Read-only database user:** configure `DATABASE_URL` with a Neon account that has read-only database permissions.
- **Statement timeout:** each query runs with a five-second PostgreSQL statement timeout.

## Evaluation

`text2sql-backend/tests.json` contains 20 in-scope Pagila questions with reference (`gold_sql`) queries and a separate list of three off-topic questions. Run `eval.py` to call SQL generation and validation directly, execute generated and reference SQL for in-scope questions, and compare results. Row order is ignored unless the reference SQL has `ORDER BY`; column names are ignored. Off-topic cases pass when the model returns no SQL. The script reports database and off-topic accuracy separately and writes details to `eval_results.json`.

Fill in the accuracy values after a complete evaluation run:

| Prompt version | Accuracy |
| --- | --- |
| Before prompt improvements | `__/20 (__%)` |
| After prompt improvements | `__/20 (__%)` |

## Local setup

### Backend

1. Create `text2sql-backend/.env` from `.env.example` and set:
   - `DATABASE_URL`: the Neon Postgres connection URL for the read-only user (include `sslmode=require` when required by Neon).
   - `GEMINI_API_KEY`: a Gemini API key whose project can access the configured model.
   - `ALLOWED_ORIGINS`: optional comma-separated browser origins. For local development, use `http://localhost:3000` (this origin is allowed by default).
2. Install dependencies and start FastAPI from the backend folder:

   ```powershell
   cd text2sql-backend
   python -m venv venv
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   .\venv\Scripts\python.exe -m uvicorn main:app --reload
   ```

   The API runs at `http://127.0.0.1:8000`.

### Frontend

1. `text2sql-frontend/.env.local` should contain:

   ```dotenv
   NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
   ```

2. Install dependencies and start Next.js from the frontend folder:

   ```powershell
   cd text2sql-frontend
   npm install
   npm run dev
   ```

   Open `http://localhost:3000`.

### Run the evaluation

With the backend environment configured and a working Gemini model/API key:

```powershell
cd text2sql-backend
.\venv\Scripts\python.exe eval.py
```

To check only the reference queries against the database, run:

```powershell
.\venv\Scripts\python.exe eval.py --check-gold
```

## Deployment

- **Render backend:** create a Web Service with root directory `text2sql-backend`, build command `pip install -r requirements.txt`, and start command `uvicorn main:app --host 0.0.0.0 --port $PORT`. Add `DATABASE_URL`, `GEMINI_API_KEY`, and `ALLOWED_ORIGINS` in the Render environment settings. Set `ALLOWED_ORIGINS` to the deployed frontend origin, for example `https://your-app.vercel.app`.
- **Vercel frontend:** import the project and set the root directory to `text2sql-frontend`. Set `NEXT_PUBLIC_API_URL` to the deployed Render backend URL, for example `https://your-api.onrender.com`.

Do not commit real credentials or `.env` files.

## Example questions

- How many films are in the database?
- What is the total payment revenue per category?
- Show the five customers with the most rentals.
