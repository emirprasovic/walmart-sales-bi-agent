GQ-01
Question: What are the total sales for each store?
SELECT
fs.store_id,
ROUND(SUM(fs.weekly_sales)::numeric, 2) AS total_sales
FROM fact_sales fs
GROUP BY fs.store_id
ORDER BY total_sales DESC;

GQ-02
Question: What were total sales in each year?
SELECT
dd.year,
ROUND(SUM(fs.weekly_sales)::numeric, 2) AS total_sales
FROM fact_sales fs
JOIN dim_date dd ON fs.date_id = dd.date_id
GROUP BY dd.year
ORDER BY dd.year ASC;

GQ-03
Question: Which month of the year generates the most sales on average?
SELECT
dd.month,
ROUND(AVG(fs.weekly_sales)::numeric, 2) AS avg_weekly_sales
FROM fact_sales fs
JOIN dim_date dd ON fs.date_id = dd.date_id
GROUP BY dd.month
ORDER BY avg_weekly_sales DESC;

GQ-04
Question: Do holiday weeks generate more revenue than non-holiday weeks on average?
SELECT
dh.holiday_name,
ROUND(AVG(fs.weekly_sales)::numeric, 2) AS avg_weekly_sales,
COUNT(*) AS week_count
FROM fact_sales fs
JOIN dim_holiday dh ON fs.holiday_id = dh.holiday_id
GROUP BY dh.holiday_name
ORDER BY avg_weekly_sales DESC;

GQ-05
Question: What was the single highest-grossing week across all stores?
SELECT
fs.date_id,
dd.year,
dd.month,
fs.store_id,
ROUND(fs.weekly_sales::numeric, 2) AS weekly_sales
FROM fact_sales fs
JOIN dim_date dd ON fs.date_id = dd.date_id
ORDER BY fs.weekly_sales DESC
LIMIT 1;

GQ-06
Question: Show me total sales per week over time.
SELECT
fs.date_id,
dd.year,
dd.month,
ROUND(SUM(fs.weekly_sales)::numeric, 2) AS total_weekly_sales
FROM fact_sales fs
JOIN dim_date dd ON fs.date_id = dd.date_id
GROUP BY fs.date_id, dd.year, dd.month
ORDER BY fs.date_id ASC;

GQ-07
Question: What is the average weekly sales when fuel price is above $3.50 vs below?
SELECT
CASE
WHEN fs.fuel_price > 3.50 THEN 'Above $3.50'
ELSE 'At or Below $3.50'
END AS fuel_price_band,
ROUND(AVG(fs.weekly_sales)::numeric, 2) AS avg_weekly_sales,
COUNT(*) AS week_count
FROM fact_sales fs
GROUP BY fuel_price_band
ORDER BY avg_weekly_sales DESC;

GQ-08
Question: How do average weekly sales compare across different unemployment rate ranges?
SELECT
CASE
WHEN fs.unemployment < 6 THEN 'Low (under 6%)'
WHEN fs.unemployment < 9 THEN 'Medium (6 to 9%)'
ELSE 'High (9% and above)'
END AS unemployment_band,
ROUND(AVG(fs.weekly_sales)::numeric, 2) AS avg_weekly_sales,
COUNT(*) AS week_count
FROM fact_sales fs
GROUP BY unemployment_band
ORDER BY avg_weekly_sales DESC;

GQ-09
Question: Rank all stores by total sales in 2011.
SELECT
fs.store_id,
ROUND(SUM(fs.weekly_sales)::numeric, 2) AS total_sales,
RANK() OVER (ORDER BY SUM(fs.weekly_sales) DESC) AS sales_rank
FROM fact_sales fs
JOIN dim_date dd ON fs.date_id = dd.date_id
WHERE dd.year = 2011
GROUP BY fs.store_id
ORDER BY sales_rank ASC;

GQ-10
Question: Show me total sales per store per year, and flag which weeks were holidays.
SELECT
dd.year,
fs.store_id,
dh.holiday_name,
ROUND(SUM(fs.weekly_sales)::numeric, 2) AS total_sales,
COUNT(*) AS week_count
FROM fact_sales fs
JOIN dim_date dd ON fs.date_id = dd.date_id
JOIN dim_holiday dh ON fs.holiday_id = dh.holiday_id
GROUP BY dd.year, fs.store_id, dh.holiday_name
ORDER BY dd.year ASC, total_sales DESC;
