import os
import re
import sys
import json
import textwrap
from pathlib import Path

from dotenv import load_dotenv

# ── Optional pretty-printing ───────────────────────────────────────────────────
try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

# ── Supabase client ────────────────────────────────────────────────────────────
try:
    from supabase import create_client, Client as SupabaseClient
except ImportError:
    print("ERROR: supabase package not found. Run: pip install supabase")
    sys.exit(1)

# ── Gemini SDK ─────────────────────────────────────────────────────────────────
try:
    import google.generativeai as genai
except ImportError:
    print("ERROR: google-generativeai not found. Run: pip install google-generativeai")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
GEMINI_MD_PATH = Path("GEMINI.md")
GEMINI_MODEL = "gemini-2.0-flash"
MAX_ROWS_DEFAULT = 100
HISTORY_LIMIT = 10


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def load_system_prompt() -> str:
    """Load GEMINI.md from project root as the agent's system instructions."""
    if not GEMINI_MD_PATH.exists():
        print(f"WARNING: {GEMINI_MD_PATH} not found — using minimal fallback prompt.")
        return (
            "You are a BI assistant. Write SQL for PostgreSQL. "
            "Return ONLY the SQL query inside a ```sql ... ``` block, nothing else, "
            "when asked a data question."
        )
    content = GEMINI_MD_PATH.read_text(encoding="utf-8")
    # Append strict SQL extraction instruction so we can parse it reliably
    content += (
        "\n\n## IMPORTANT OUTPUT RULE\n"
        "When generating SQL, always wrap it in a ```sql ... ``` fenced block. "
        "Do NOT include multiple SQL statements. "
        "Do NOT include DML (INSERT/UPDATE/DELETE/DROP/TRUNCATE)."
    )
    return content


def extract_sql(text: str) -> str | None:
    """Pull the first ```sql ... ``` block out of the model's response."""
    pattern = r"```sql\s*([\s\S]*?)```"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: look for a bare SELECT statement
    select_match = re.search(r"(SELECT\s+[\s\S]+?;)", text, re.IGNORECASE)
    if select_match:
        return select_match.group(1).strip()
    return None


def is_safe_sql(sql: str) -> bool:
    """Reject any DML/DDL that could mutate data."""
    forbidden = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE)\b",
        re.IGNORECASE,
    )
    return not bool(forbidden.search(sql))


def run_query(supabase: SupabaseClient, sql: str) -> tuple[list[dict], str | None]:
    """
    Execute raw SQL via Supabase's PostgREST RPC endpoint.
    Returns (rows, error_message).
    """
    try:
        # supabase-py v2: use .rpc() with a SQL runner function, or use
        # the postgrest client directly for arbitrary SQL via the /rest/v1/rpc
        # The cleanest approach for arbitrary SQL is via psycopg2 with the
        # connection string, but we keep it dependency-light here with the
        # Supabase client's built-in SQL execution.
        response = supabase.rpc("execute_sql", {"query": sql}).execute()
        # If you don't have an execute_sql function, fall back to direct pg
        return response.data or [], None
    except Exception as e:
        # Fallback: try direct PostgreSQL connection via psycopg2 if available
        print("Falling back to psycopg2 connection")
        return _run_via_psycopg2(sql, str(e))


def _run_via_psycopg2(sql: str, original_error: str) -> tuple[list[dict], str | None]:
    """Fallback: connect directly with psycopg2 using individual env vars."""
    try:
        import psycopg2
        import psycopg2.extras

        # Accept either a full DATABASE_URL or individual vars
        db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
        if db_url:
            conn = psycopg2.connect(db_url)
        else:
            conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                database=os.getenv("POSTGRES_DATABASE") or os.getenv("POSTGRES_DB"),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
            )

        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows, None

    except ImportError:
        return [], (
            f"Supabase RPC error: {original_error}\n"
            "psycopg2 not installed either. Run: pip install psycopg2-binary\n"
            "Or add an execute_sql function to your Supabase project."
        )
    except Exception as e:
        return [], f"Database error: {e}"


def format_rows(rows: list[dict]) -> str:
    """Render query results as a table."""
    if not rows:
        return "(no rows returned)"
    if HAS_TABULATE:
        return tabulate(rows, headers="keys", tablefmt="rounded_outline",
                        floatfmt=".2f", maxcolwidths=40)
    # Plain fallback
    headers = list(rows[0].keys())
    lines = [" | ".join(headers)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(" | ".join(str(v) for v in row.values()))
    return "\n".join(lines)


def print_divider(char="─", width=70):
    print(char * width)


def wrap(text: str, width: int = 70) -> str:
    return "\n".join(
        textwrap.fill(line, width) if line.strip() else line
        for line in text.splitlines()
    )


# ══════════════════════════════════════════════════════════════════════════════
# AGENT LOOP
# ══════════════════════════════════════════════════════════════════════════════

def build_interpretation_prompt(question: str, sql: str, rows: list[dict]) -> str:
    """Ask Gemini to interpret the results in plain English."""
    sample = rows[:20]  # don't blow the context with huge result sets
    return (
        f"The user asked: \"{question}\"\n\n"
        f"You ran this SQL:\n```sql\n{sql}\n```\n\n"
        f"The result ({len(rows)} rows total, showing up to 20):\n"
        f"{json.dumps(sample, indent=2, default=str)}\n\n"
        "Write a clear, concise plain-English summary of what this data shows. "
        "Highlight key numbers, trends, or anomalies. Keep it to 3–5 sentences."
    )


def run_agent():
    # ── Validate config ────────────────────────────────────────────────────────
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_KEY (or SUPABASE_KEY)")
    if missing:
        print("ERROR: Missing environment variables:", ", ".join(missing))
        print("Create a .env file with these values and try again.")
        sys.exit(1)

    # ── Init clients ───────────────────────────────────────────────────────────
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=load_system_prompt(),
    )
    supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
    chat = model.start_chat(history=[])

    # ── Welcome ────────────────────────────────────────────────────────────────
    print_divider("═")
    print("  📊  BI Agent  —  Powered by Gemini + Supabase")
    print_divider("═")
    print(f"  Model : {GEMINI_MODEL}")
    print(f"  Schema: {GEMINI_MD_PATH} {'✓' if GEMINI_MD_PATH.exists() else 'X (not found)'}")
    print(f"  DB    : {SUPABASE_URL}")
    print_divider()
    print("  Ask any business question. Type 'exit' or 'quit' to stop.")
    print("  Type 'history' to see recent queries.\n")

    query_history: list[dict] = []

    while True:
        try:
            print_divider()
            question = input("  🟢 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break

        if not question:
            continue

        lower = question.lower()

        if lower in ("exit", "quit", "bye"):
            print("Goodbye!")
            break

        if lower == "history":
            if not query_history:
                print("  (no queries yet)")
            else:
                for i, item in enumerate(query_history[-HISTORY_LIMIT:], 1):
                    print(f"\n  [{i}] Q: {item['question']}")
                    print(f"       SQL: {item['sql'][:80]}{'...' if len(item['sql']) > 80 else ''}")
                    print(f"       Rows: {item['row_count']}")
            continue

        # ── Step 1: Ask Gemini for SQL ─────────────────────────────────────────
        print("\n  ⏳ Generating SQL...", end="", flush=True)
        try:
            sql_response = chat.send_message(question)
            response_text = sql_response.text
        except Exception as e:
            print(f"\n  ❌ Gemini API error: {e}")
            continue

        sql = extract_sql(response_text)

        if not sql:
            # Gemini answered conversationally (clarifying question, etc.)
            print("\n")
            print_divider("·")
            print(f"  🤖 Agent:\n{wrap(response_text)}")
            continue

        if not is_safe_sql(sql):
            print("\n  ⛔ Rejected: query contains forbidden DML/DDL statements.")
            continue

        # Enforce row limit if not already present
        if "LIMIT" not in sql.upper():
            sql = sql.rstrip(";") + f"\nLIMIT {MAX_ROWS_DEFAULT};"

        print(" done.\n")

        # ── Step 2: Execute SQL ────────────────────────────────────────────────
        print("  ⏳ Querying database...", end="", flush=True)
        rows, error = run_query(supabase, sql)

        if error:
            print(f"\n  ❌ Database error:\n  {error}")
            # Feed error back to Gemini so it can self-correct
            try:
                correction_prompt = (
                    f"The SQL you generated caused this error:\n{error}\n\n"
                    f"Original SQL:\n```sql\n{sql}\n```\n\n"
                    "Please correct the SQL and return only the fixed ```sql ... ``` block."
                )
                print("\n  🔄 Asking Gemini to self-correct...", end="", flush=True)
                retry_response = chat.send_message(correction_prompt)
                fixed_sql = extract_sql(retry_response.text)
                if fixed_sql and is_safe_sql(fixed_sql):
                    if "LIMIT" not in fixed_sql.upper():
                        fixed_sql = fixed_sql.rstrip(";") + f"\nLIMIT {MAX_ROWS_DEFAULT};"
                    rows, error2 = run_query(supabase, fixed_sql)
                    if not error2:
                        sql = fixed_sql
                        print(" fixed!\n")
                    else:
                        print(f"\n  ❌ Retry also failed: {error2}")
                        continue
                else:
                    print("\n  ❌ Could not extract corrected SQL.")
                    continue
            except Exception as e:
                print(f"\n  ❌ Self-correction error: {e}")
                continue
        else:
            print(" done.\n")

        # ── Step 3: Display results ────────────────────────────────────────────
        print_divider("·")
        print(f"  📋 Results ({len(rows)} rows):\n")
        print(format_rows(rows))

        # ── Step 4: Interpret results in plain English ─────────────────────────
        if rows:
            print()
            print("  ⏳ Interpreting results...", end="", flush=True)
            try:
                interp_prompt = build_interpretation_prompt(question, sql, rows)
                interp_response = chat.send_message(interp_prompt)
                print(" done.\n")
                print_divider("·")
                print(f"  🤖 Summary:\n")
                print(wrap(interp_response.text, width=68))
            except Exception as e:
                print(f"\n  ⚠️  Could not interpret results: {e}")

        # ── Step 5: Show SQL ───────────────────────────────────────────────────
        print()
        print_divider("·")
        print("  🔍 SQL used:\n")
        for line in sql.splitlines():
            print(f"     {line}")

        # ── Log to history ─────────────────────────────────────────────────────
        query_history.append({
            "question": question,
            "sql": sql,
            "row_count": len(rows),
        })
        if len(query_history) > HISTORY_LIMIT:
            query_history.pop(0)

        print()


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_agent()