# Deploying on Render

Create a Render **Web Service** from this repository and set its **Root Directory** to `text2sql-backend`.

- **Runtime:** Python 3
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT` (also provided by `Procfile`)

Add these environment variables in the Render service settings:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Neon Postgres connection URL for the read-only database user. Include `sslmode=require` when required by your Neon connection string. |
| `GEMINI_API_KEY` | API key for the Google Gemini project used by the application. |
| `GROQ_API_KEY` | Optional Groq API key used if Gemini generation fails. |
| `GROQ_MODEL` | Optional Groq model ID for fallback generation; defaults to `openai/gpt-oss-120b`. |
| `ALLOWED_ORIGINS` | Comma-separated browser origins allowed to call this API, such as `https://your-frontend.onrender.com`. Do not include paths or trailing slashes. |

Render sets `PORT` for the service; the Procfile uses it automatically. The app also allows `http://localhost:3000` for local frontend development.

Do not commit the real `.env` file or put credentials in source control. Use Render's environment variable settings for deployed secrets.
