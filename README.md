Here is the updated `README.md` reflecting the Walmart Sales ETL process and the Conversational BI Agent.

---

# Walmart Sales Data Warehouse & BI Agent

This project implements a Star Schema data warehouse using PostgreSQL and a Python-based ETL process for the Walmart Sales dataset. It also includes a Conversational BI Agent that allows users to query the database using natural language via Groq or Gemini.

## Project Structure

- `walmart_sales.csv`: Source dataset containing retail transactions.
- `etl_process.py`: Main ETL script (Extract, Transform, Load) for the Walmart data.
- `bi_agent_groq.py`: Natural language BI Assistant powered by Groq (Llama 3).
- `bi_agent_gemini.py`: Natural language BI Assistant powered by Google Gemini.
- `GROQ.md` / `GEMINI.md`: System instructions and schema metadata for the AI models.
- `.env`: Database credentials and API keys.

## Star Schema Design

The data is organized into a Star Schema optimized for retail analytics:

- **Fact Table**: `fact_sales`
  - Metrics: `weekly_sales`, `temperature`, `fuel_price`, `cpi`, `unemployment`.
- **Dimension Tables**:
  - `dim_store`: Store identifiers.
  - `dim_date`: Time dimension (day, month, year).
  - `dim_holiday`: Holiday categorization (Holiday vs. Non-Holiday).

## Prerequisites

- Python 3.10+
- PostgreSQL database (or Supabase instance)
- API Keys for [Groq](https://console.groq.com/) or [Google AI Studio](https://aistudio.google.com/)

## Setup Instructions

1. **Install Dependencies**:

   ```bash
   pip install pandas psycopg2-binary sqlalchemy python-dotenv groq google-generativeai supabase tabulate
   ```

2. **Configure Environment**:
   Create a `.env` file in the root directory:

   ```env
   # Database (Postgres or Supabase)
   POSTGRES_HOST=your_host
   POSTGRES_PORT=5432
   POSTGRES_DATABASE=postgres
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=your_password

   # Supabase (For BI Agent API access)
   SUPABASE_URL=your_url
   SUPABASE_KEY=your_service_role_key

   # AI Model Keys
   GROQ_API_KEY=your_groq_key
   GEMINI_API_KEY=your_gemini_key
   ```

3. **Run ETL Process**:
   Load and clean the Walmart data into your PostgreSQL instance:

   ```bash
   python etl_process.py
   ```

4. **Launch the BI Agent**:
   Query your data using natural language:
   ```bash
   python bi_agent_groq.py
   # OR
   python bi_agent_gemini.py
   ```

## Conversational BI Agent

The BI Agent acts as a bridge between natural language and your SQL database.

1. **Natural Language to SQL**: User asks "Which store had the highest sales during holidays?"
2. **SQL Generation**: The agent uses `GROQ.md` or `GEMINI.md` to understand the schema and generate valid PostgreSQL.
3. **Execution**: The query is executed via Supabase RPC or `psycopg2`.
4. **Interpretation**: The agent receives the raw data and provides a plain-English summary of the findings.

## Development Prompts Sequence

This project evolved through the following prompt sequence:

### 1. Walmart ETL Implementation

- `can you update this etl script so it references walmart_sales.csv with the following columns: Store, Date, Weekly_Sales, Holiday_Flag, Temperature, Fuel_Price, CPI, Unemployment`
- `normalize the schema into fact_sales, dim_store, dim_date, and dim_holiday.`
- `ensure date parsing handles DD-MM-YYYY format and use ON CONFLICT for idempotency.`

### 2. BI Agent Development

- `create a BI agent script that connects to Supabase and uses Gemini to turn questions into SQL.`
- `update the script to use Groq API via GROQ_API_KEY and use GROQ.md for the system prompt.`
- `fix the SyntaxError regarding backslashes in f-strings for Python versions < 3.12.`
- `add a fallback to psycopg2 if the Supabase RPC "execute_sql" function is not found.`

### 3. Database Functions (Supabase)

To enable the Agent to run queries via the API, the following was implemented in the Supabase SQL editor:

```sql
create or replace function execute_sql(query text)
returns json language plpgsql security definer as $$
begin
  return (select json_agg(t) from (execute query) t);
end; $$;
```

## Key Features

- **Automated Schema Mapping**: AI agents automatically handle joins between fact and dimension tables.
- **Self-Correction**: If the AI generates an invalid SQL query, the agent feeds the error back to the model for a second attempt.
- **Batch ETL**: `etl_process.py` uses batching (1000 rows) to ensure memory stability during large CSV uploads.
- **Idempotency**: All tables use `ON CONFLICT DO NOTHING` to allow for repeated ETL runs without data duplication.
