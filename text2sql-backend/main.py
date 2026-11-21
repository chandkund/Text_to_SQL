"""FastAPI service for answering natural language questions with Pagila SQL."""

import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from groq import Groq
from pydantic import BaseModel
import sqlglot
from sqlglot import exp

load_dotenv()

ALLOWED_TABLES = {
    "film", "actor", "film_actor", "category", "film_category",
    "inventory", "rental", "payment", "customer", "store",
}
JOIN_HINTS = (
    "film_actor links film and actor; film_category links film and category; "
    "inventory links film and store; rental links inventory and customer; "
    "payment links rental and customer. Also, payment.customer_id directly links "
    "payment to customer; payment.rental_id links payment to rental."
)
TABLE_GUIDE = """Table and important-column guide:
film: One row per movie. film_id is the key; title, release_year, rating, length, rental_duration, rental_rate, replacement_cost, and special_features describe the movie.
actor: One row per actor. actor_id is the key; first_name and last_name are the actor's names.
film_actor: Bridge table assigning actors to films. Its film_id and actor_id form the relationship to film and actor.
category: Movie categories. category_id is the key and name is the category label.
film_category: Bridge table assigning films to categories, using film_id and category_id.
inventory: One physical film copy per inventory_id. film_id identifies the movie and store_id identifies its store; count inventory_id to count copies.
rental: One rental transaction per rental_id. inventory_id identifies the rented copy, customer_id identifies the renter, rental_date is checkout time, and return_date is nullable until returned.
payment: One payment per payment_id. customer_id identifies the paying customer, rental_id links an associated rental, amount is the money paid, and payment_date is when it was paid.
customer: One customer per customer_id. store_id identifies the home store; first_name, last_name, email, and active describe the customer.
store: One store per store_id. manager_staff_id identifies its manager and address_id identifies its address.

Five examples (use these to learn schema and query patterns; adapt them to the question):
Question: What is the average movie length for each rating?
SQL: SELECT rating, AVG(length) AS average_length FROM film GROUP BY rating ORDER BY rating

Question: How many actors have a last name starting with N?
SQL: SELECT COUNT(*) AS actor_count FROM actor WHERE last_name LIKE 'N%'

Question: How many inventory copies are held by each store?
SQL: SELECT store_id, COUNT(inventory_id) AS copy_count FROM inventory GROUP BY store_id ORDER BY store_id

Question: Which customers have made at least 20 payments?
SQL: SELECT c.customer_id, c.first_name, c.last_name, COUNT(p.payment_id) AS payment_count FROM customer AS c JOIN payment AS p ON p.customer_id = c.customer_id GROUP BY c.customer_id, c.first_name, c.last_name HAVING COUNT(p.payment_id) >= 20 ORDER BY c.customer_id

Question: What is the average time to return films, in days?
SQL: SELECT AVG(EXTRACT(EPOCH FROM (return_date - rental_date)) / 86400.0) AS average_days FROM rental WHERE return_date IS NOT NULL"""
SYSTEM_RULES = (
    "For an in-scope question, write exactly one read-only PostgreSQL SELECT using "
    "only the listed public tables. "
    "Use the actual column names and join keys shown; do not invent columns or infer "
    "relationships from similarly named fields. Aggregate at the requested grain, "
    "avoid multiplying amounts by joining unrelated detail rows, and use PostgreSQL "
    "date and interval syntax. Include a useful ORDER BY when the question asks for "
    "a ranking or ordered list. If the question cannot be answered using the listed "
    "tables and columns (including general knowledge, weather, chit-chat, or data "
    "outside this database), do not generate SQL. Instead return JSON with sql set "
    "to null and explanation set to one short, friendly sentence saying this assistant "
    "answers questions about the Pagila database and giving an example question. "
    "For an in-scope question, return JSON with a SQL string and a short explanation. "
    "Always return exactly the keys sql and explanation."
)

app = FastAPI(title="Text-to-SQL Assistant")
origins = ["http://localhost:3000"]
origins.extend(o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip())
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

schema_prompt = ""
gemini_client = None
groq_client = None
groq_model = "openai/gpt-oss-120b"
gemini_model = "gemini-3.8-flash"


class AskRequest(BaseModel):
    question: str


def get_connection():
    """Open a Postgres connection using the configured read-only account."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(database_url)


@app.on_event("startup")
def load_schema_and_client():
    """Read the permitted schema once and prepare the Gemini client."""
    global schema_prompt, gemini_client, groq_client, groq_model, gemini_model
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT table_name, column_name, data_type
                   FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = ANY(%s)
                   ORDER BY table_name, ordinal_position""",
                (list(ALLOWED_TABLES),),
            )
            schema: dict[str, list[str]] = {name: [] for name in sorted(ALLOWED_TABLES)}
            for table, column, data_type in cursor.fetchall():
                schema[table].append(f"{column} ({data_type})")

    discovered_schema = "\n".join(
        f"{table}: {', '.join(columns) if columns else '(not found)'}"
        for table, columns in schema.items()
    )
    schema_prompt = (
        f"{discovered_schema}\n\n{TABLE_GUIDE}\n\nJoin hints: {JOIN_HINTS}"
    )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    gemini_client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=8_000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )

    # Groq is optional and is only used if Gemini generation fails.
    groq_api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_client = Groq(api_key=groq_api_key, timeout=12.0) if groq_api_key else None


def validate_sql(sql: str) -> str:
    """Allow one SELECT over permitted tables and ensure a bounded result."""
    try:
        statements = [statement for statement in sqlglot.parse(sql, read="postgres") if statement]
    except sqlglot.errors.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid SQL: {exc}") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise HTTPException(status_code=400, detail="Only one SELECT statement is allowed")

    query = statements[0]
    cte_names = {cte.alias_or_name.lower() for cte in query.find_all(exp.CTE)}
    for table in query.find_all(exp.Table):
        name = table.name.lower()
        database = table.db.lower()
        if (database and database != "public") or (name not in ALLOWED_TABLES and name not in cte_names):
            raise HTTPException(status_code=400, detail=f"Table is not allowed: {table.sql(dialect='postgres')}")

    if query.args.get("into") is not None:
        raise HTTPException(status_code=400, detail="SELECT INTO is not allowed")
    if query.args.get("limit") is None:
        query = query.limit(100)
    return query.sql(dialect="postgres")


def json_value(value: Any) -> Any:
    """Convert common Postgres values to JSON-compatible representations."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def generate_sql(question: str) -> dict[str, str | None]:
    """Ask Gemini first, then Groq on failure; return SQL and explanation only."""
    if gemini_client is None:
        raise RuntimeError("Service is not initialized; load the schema and Gemini client first")
    system_prompt = f"{SYSTEM_RULES}\n\nSchema and guidance:\n{schema_prompt}"

    try:
        # The Google SDK retries transient Gemini errors before this fallback runs.
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=f"{system_prompt}\n\nQuestion:\n{question}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema={"type": "OBJECT", "properties": {
                    "sql": {"type": "STRING", "nullable": True},
                    "explanation": {"type": "STRING"}
                }, "required": ["sql", "explanation"]},
            ),
        )
        generated = json.loads(response.text)
        sql = generated.get("sql")
        if "sql" not in generated or (sql is not None and not isinstance(sql, str)) or not isinstance(generated.get("explanation"), str):
            raise ValueError("Gemini response must contain sql as a string or null and a string explanation")
        return generated
    except Exception as gemini_error:
        if groq_client is None:
            raise RuntimeError(
                f"Gemini SQL generation failed and Groq fallback is not configured: {gemini_error}"
            ) from gemini_error

        try:
            response = groq_client.chat.completions.create(
                model=groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            generated = json.loads(content)
            sql = generated.get("sql")
            if "sql" not in generated or (sql is not None and not isinstance(sql, str)) or not isinstance(generated.get("explanation"), str):
                raise ValueError("Groq response must contain sql as a string or null and a string explanation")
            return generated
        except Exception as groq_error:
            raise RuntimeError(
                f"Gemini SQL generation failed ({gemini_error}); Groq fallback failed ({groq_error})"
            ) from groq_error


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty")
    if gemini_client is None:
        raise HTTPException(status_code=503, detail="Service is not initialized")

    try:
        generated = generate_sql(request.question)
        if not generated["sql"]:
            return {
                "sql": None,
                "columns": [],
                "rows": [],
                "explanation": generated["explanation"],
                "off_topic": True,
            }
        sql = validate_sql(generated["sql"])
        explanation = generated["explanation"]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SQL generation failed: {exc}") from exc

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                # Apply a five second timeout to this transaction's query.
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                cursor.execute(sql)
                columns = [description[0] for description in cursor.description]
                rows = [[json_value(value) for value in row] for row in cursor.fetchall()]
        return {"sql": sql, "columns": columns, "rows": rows, "explanation": explanation}
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail=f"Query execution failed: {exc.pgerror or str(exc)}") from exc
