# UW Snack Overflow - Transaction Data Analysis

This repository contains transaction data from UW Snack Overflow and provides data visualization scripts to analyze sales, profitability, items, and other key metrics.

## Data Overview

The transaction data spans from **September 1, 2025 to November 13, 2025** and includes:
- Sales information (Gross Sales, Net Sales, Net Total)
- Transaction fees
- Item descriptions
- Payment methods
- Customer information
- Time and date stamps

## Setup

### Prerequisites

Install the required Python packages:

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install pandas matplotlib seaborn numpy
```

### Data File

The main data file is: `transactions-2025-09-01-2025-11-13.csv`

## Data Visualizations

The `visualize_transactions.py` script generates comprehensive visualizations covering cost analysis, profitability, item performance, and sales trends.

### Running the Analysis

Run the visualization script:

```bash
python visualize_transactions.py
```

## Generated Visualizations

The script generates the following visualizations in the `visualizations/` directory:

1. **Fees Over Time** - Daily transaction fees trend
2. **Fees Distribution** - Histogram of fee amounts
3. **Gross vs Net Sales** - Comparison of gross sales and net total after fees
4. **Profit Margin** - Average profit margin percentage over time
5. **Revenue Breakdown** - Total gross sales, fees, and net revenue
6. **Top Items by Sales** - Top 20 items ranked by gross sales
7. **Top Items by Frequency** - Top 15 items by transaction count
8. **Daily Sales Trends** - Daily sales amounts and transaction counts
9. **Hourly Patterns** - Sales and transaction patterns by hour of day
10. **Payment Methods** - Distribution of sales and transactions by payment type

## Key Metrics Analyzed

- **Cost Analysis**: Transaction fees, fee distribution, and fee impact on revenue
- **Profitability**: Gross vs net sales, profit margins, revenue breakdown
- **Item Performance**: Top-selling items by revenue and frequency
- **Sales Trends**: Daily and hourly patterns in sales and transactions
- **Payment Methods**: Distribution across card, cash, and other payment types

## Notes

- All currency values are automatically cleaned and converted to numeric format
- Items are extracted from the Description column, handling multiple items per transaction
- The script handles missing data and edge cases gracefully
- All plots are saved as high-resolution PNG files (300 DPI) for presentations

## Requirements

- Python 3.7+
- pandas
- matplotlib
- seaborn
- numpy

