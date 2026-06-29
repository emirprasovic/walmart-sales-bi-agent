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

# ── Groq SDK ───────────────────────────────────────────────────────────────────
try:
    from groq import Groq
except ImportError:
    print("ERROR: groq package not found. Run: pip install groq")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
PROMPT_MD_PATH = Path("prompt.md")
# Recommended models: llama-3.3-70b-versatile or mixtral-8x7b-32768
GROQ_MODEL = "llama-3.3-70b-versatile" 
MAX_ROWS_DEFAULT = 100
HISTORY_LIMIT = 10


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def load_system_prompt() -> str:
    """Load GROQ.md from project root as the agent's system instructions."""
    if not PROMPT_MD_PATH.exists():
        print(f"WARNING: {PROMPT_MD_PATH} not found — using minimal fallback prompt.")
        return (
            "You are a BI assistant. Write SQL for PostgreSQL. "
            "Return ONLY the SQL query inside a ```sql ... ``` block, nothing else, "
            "when asked a data question."
        )
    content = PROMPT_MD_PATH.read_text(encoding="utf-8")
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
    """Execute raw SQL via Supabase RPC or fallback to psycopg2."""
    try:
        response = supabase.rpc("execute_sql", {"query": sql}).execute()
        return response.data or [], None
    except Exception as e:
        return _run_via_psycopg2(sql, str(e))


def _run_via_psycopg2(sql: str, original_error: str) -> tuple[list[dict], str | None]:
    try:
        import psycopg2
        import psycopg2.extras
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
    except Exception as e:
        return [], f"Database error: {e}"


def format_rows(rows: list[dict]) -> str:
    if not rows: return "(no rows returned)"
    if HAS_TABULATE:
        return tabulate(rows, headers="keys", tablefmt="rounded_outline", floatfmt=".2f", maxcolwidths=40)
    return str(rows[0].keys()) + "\n" + "-"*20 # Very basic fallback


def print_divider(char="─", width=70):
    print(char * width)


def wrap(text: str, width: int = 70) -> str:
    return "\n".join(textwrap.fill(line, width) if line.strip() else line for line in text.splitlines())


# ══════════════════════════════════════════════════════════════════════════════
# AGENT LOOP
# ══════════════════════════════════════════════════════════════════════════════

def run_agent():
    # ── Validate config ────────────────────────────────────────────────────────
    missing = []
    if not GROQ_API_KEY: missing.append("GROQ_API_KEY")
    if not SUPABASE_URL: missing.append("SUPABASE_URL")
    if not SUPABASE_KEY: missing.append("SUPABASE_SERVICE_KEY")
    if missing:
        print("ERROR: Missing environment variables:", ", ".join(missing))
        sys.exit(1)

    # ── Init clients ───────────────────────────────────────────────────────────
    client = Groq(api_key=GROQ_API_KEY)
    supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Groq uses a message list to maintain history
    system_prompt = load_system_prompt()
    messages = [{"role": "system", "content": system_prompt}]

    # ── Welcome ────────────────────────────────────────────────────────────────
    print_divider("═")
    print("  📊  BI Agent  —  Powered by Groq + Supabase")
    print_divider("═")
    print(f"  Model : {GROQ_MODEL}")
    print(f"  Schema: {PROMPT_MD_PATH} {'✓' if PROMPT_MD_PATH.exists() else 'X (not found)'}")
    print_divider()

    query_history: list[dict] = []

    while True:
        try:
            print_divider()
            question = input("  🟢 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not question: continue
        if question.lower() in ("exit", "quit", "bye"): break

        if question.lower() == "history":
            for i, item in enumerate(query_history[-HISTORY_LIMIT:], 1):
                print(f"\n  [{i}] Q: {item['question']}\n       Rows: {item['row_count']}")
            continue

        # ── Step 1: Ask Groq for SQL ──────────────────────────────────────────
        print("\n  ⏳ Generating SQL...", end="", flush=True)
        messages.append({"role": "user", "content": question})
        
        try:
            completion = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.1,
            )
            response_text = completion.choices[0].message.content
            messages.append({"role": "assistant", "content": response_text})
        except Exception as e:
            print(f"\n  ❌ Groq API error: {e}")
            continue

        sql = extract_sql(response_text)

        if not sql:
            print("\n")
            print_divider("·")
            print(f"  🤖 Agent:\n{wrap(response_text)}")
            continue

        if not is_safe_sql(sql):
            print("\n  ⛔ Rejected: unsafe SQL detected.")
            continue

        if "LIMIT" not in sql.upper():
            sql = sql.rstrip(";") + f"\nLIMIT {MAX_ROWS_DEFAULT};"

        print(" done.\n")

        # ── Step 2: Execute SQL ────────────────────────────────────────────────
        print("  ⏳ Querying database...", end="", flush=True)
        rows, error = run_query(supabase, sql)

        if error:
            print(f"\n  ❌ Database error: {error}")
            # Self-correction logic
            correction_prompt = f"The SQL caused an error: {error}. Please fix the SQL."
            messages.append({"role": "user", "content": correction_prompt})
            
            try:
                print("  🔄 Self-correcting...", end="", flush=True)
                retry_comp = client.chat.completions.create(model=GROQ_MODEL, messages=messages)
                fixed_sql = extract_sql(retry_comp.choices[0].message.content)
                if fixed_sql:
                    rows, error = run_query(supabase, fixed_sql)
                    if not error: sql = fixed_sql; print(" fixed!")
            except Exception:
                print(" failed correction.")
                continue
        else:
            print(" done.\n")

        # ── Step 3: Display results ────────────────────────────────────────────
        print_divider("·")
        print(f"  📋 Results ({len(rows)} rows):\n")
        print(format_rows(rows))

        # ── Step 4: Interpretation ─────────────────────────────────────────────
        if rows:
            print("\n  ⏳ Interpreting...", end="", flush=True)
            interp_prompt = (
                f"The result set has {len(rows)} rows. Here is a sample: {json.dumps(rows[:10], default=str)}. "
                "Summarize these results in 3-5 sentences for the user."
            )
            try:
                interp_comp = client.chat.completions.create(
                    model=GROQ_MODEL, 
                    messages=[{"role": "system", "content": "You are a helpful data analyst."}, 
                              {"role": "user", "content": interp_prompt}]
                )
                print(" done.\n")
                print_divider("·")
                print(f"  🤖 Summary:\n\n{wrap(interp_comp.choices[0].message.content, 68)}")
            except Exception:
                print(" interpretation failed.")

        # ── Step 5: Show SQL ───────────────────────────────────────────────────
        clean_sql = sql.replace('\n', ' ')
        print(f"\n  🔍 SQL: {clean_sql}")

        query_history.append({"question": question, "sql": sql, "row_count": len(rows)})
        if len(messages) > 20: # Keep context window lean
            messages = [messages[0]] + messages[-10:]

if __name__ == "__main__":
    run_agent()