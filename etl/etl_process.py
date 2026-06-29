import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_connection():
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DATABASE"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )

def insert_batches(cur, query, data, batch_size=1000, table_name=""):
    """Inserts data in batches and logs progress."""
    total = len(data)
    if total == 0:
        logging.info(f"No data to insert into {table_name}.")
        return
        
    for i in range(0, total, batch_size):
        batch = data[i:i + batch_size]
        execute_values(cur, query, batch)
        logging.info(f"Inserted {min(i + batch_size, total)}/{total} rows into {table_name}")

def run_etl():
    logging.info("Starting Walmart Sales ETL process...")
    
    # Load Source Data
    try:
        df = pd.read_csv('walmart_sales.csv')
    except FileNotFoundError:
        logging.error("walmart_sales.csv not found.")
        return

    df = df.drop_duplicates()
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        stores = df[['Store']].drop_duplicates().sort_values('Store')
        insert_batches(cur, """
            INSERT INTO public.dim_store (store_id)
            VALUES %s
            ON CONFLICT (store_id) DO NOTHING
        """, stores.values.tolist(), table_name="dim_store")
        
        dates = df[['Date']].drop_duplicates()
        date_data = [(
            d, d.day, d.month, d.year
        ) for d in dates['Date']]
        insert_batches(cur, """
            INSERT INTO public.dim_date (date_id, day, month, year)
            VALUES %s
            ON CONFLICT (date_id) DO NOTHING
        """, date_data, table_name="dim_date")
        
        holiday_mapping = pd.DataFrame([
            (0, 'Non-Holiday'),
            (1, 'Holiday')
        ], columns=['holiday_id', 'holiday_name'])
        insert_batches(cur, """
            INSERT INTO public.dim_holiday (holiday_id, holiday_name)
            VALUES %s
            ON CONFLICT (holiday_id) DO NOTHING
        """, holiday_mapping.values.tolist(), table_name="dim_holiday")
        
        cur.execute("SELECT date_id FROM public.dim_date")
        
        # Prepare fact table data
        fact_data = []
        for row in df.itertuples(index=False):
            fact_data.append((
                int(row.Store),
                row.Date,
                int(row.Holiday_Flag),
                float(row.Weekly_Sales),
                float(row.Temperature),
                float(row.Fuel_Price),
                float(row.CPI),
                float(row.Unemployment)
            ))
        
        logging.info(f"Total rows to insert into fact_sales: {len(fact_data)}")
        
        insert_batches(cur, """
            INSERT INTO public.fact_sales (
                store_id, date_id, holiday_id, weekly_sales, 
                temperature, fuel_price, cpi, unemployment
            )
            VALUES %s
        """, fact_data, table_name="fact_sales")
        
        conn.commit()
        logging.info("ETL process completed successfully.")
        
    except Exception as e:
        conn.rollback()
        logging.error(f"An error occurred: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_etl()