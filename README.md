# Online Retail Data Warehouse ETL

This project implements a Star Schema data warehouse using PostgreSQL and a Python-based ETL process for the "Online Retail" dataset.

## Project Structure

- `OnlineRetail.csv`: Source dataset containing transactions.
- `etl_process.py`: Main ETL script (Extract, Transform, Load).
- `.env`: Database connection credentials.
- `requirements.txt`: Python dependencies.

## Star Schema Design

The data is organized into a Star Schema for optimized analytical querying:

- **Fact Table**: `fact_sales` (measures: quantity, unit_price, total_amount)
- **Dimension Tables**:
  - `dim_product`: Product descriptions and stock codes.
  - `dim_customer`: Customer IDs and geographical information.
  - `dim_date`: Granular time dimension (year, month, day, quarter, hour, day of week).

## Prerequisites

- Python 3.10+
- PostgreSQL database
- Virtual environment (recommended)

## Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Create a `.env` file in the root directory with your PostgreSQL credentials:
   ```env
   POSTGRES_HOST=your_host
   POSTGRES_PORT=5432
   POSTGRES_DATABASE=online-retail-dw
   POSTGRES_USER=your_user
   POSTGRES_PASSWORD=your_password
   ```

3. **Run ETL Process**:
   Execute the Python script to clean the data and populate the database:
   ```bash
   python etl_process.py
   ```

## Built with Gemini CLI

This project was developed using the Gemini CLI with the PostgreSQL extension.

### PostgreSQL Extension Configuration

The Gemini CLI uses the following environment variables to interact with the database. These should be set in your terminal session or stored in a `.env` file (the CLI automatically detects local `.env` files).

```bash
export POSTGRES_HOST="your-db-host"
export POSTGRES_PORT="5432"
export POSTGRES_DATABASE="online-retail-dw"
export POSTGRES_USER="your-user"
export POSTGRES_PASSWORD="your-password"
```

### Example Development Prompts

Here is the sequence of prompts used to generate this project:

1.  **Data Analysis**:
    `analyze first 5 lines of the @OnlineRetail.csv file and create me a start schema for the data warehouse. create dim_product, dim_date, dim_customer and fact_sales tables.`
2.  **Schema Implementation**:
    `implement this schema using postgres extension`
3.  **ETL Script Generation**:
    `generate a python ETL script named etl_process.py that uses pandas and psycopg2 to load OnlineRetail.csv into the postgres tables. handle deduplication, null customer IDs, and use surrogate keys for the fact table. implement batching and idempotency with ON CONFLICT.`


## Key Features

- **Idempotent Loads**: Uses `ON CONFLICT` clauses to prevent duplicate data if the script is run multiple times.
- **Data Cleaning**: Handles missing customer IDs, deduplicates records, and calculates `total_amount`.
- **Batch Processing**: Inserts data in batches of 1000 rows for better performance and memory management.
