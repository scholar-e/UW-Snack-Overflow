import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime
import re
import os

# Set style for better-looking plots
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)

# Load the data
df = pd.read_csv('transactions-2025-09-01-2025-11-13.csv')

# Helper function to clean currency values
def clean_currency(value):
    """Convert currency strings to float"""
    if pd.isna(value) or value == '':
        return 0.0
    if isinstance(value, str):
        # Remove $ and commas
        value = value.replace('$', '').replace(',', '').strip()
        # Handle negative values
        if value.startswith('-'):
            return -float(value[1:])
        return float(value)
    return float(value)

# Clean numeric columns
numeric_cols = ['Gross Sales', 'Discounts', 'Net Sales', 'Fees', 'Net Total', 
                'Total Collected', 'Card', 'Cash', 'Tip']
for col in numeric_cols:
    if col in df.columns:
        df[col] = df[col].apply(clean_currency)

# Convert Date to datetime
df['Date'] = pd.to_datetime(df['Date'])
df['DateTime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))

# Create output directory for plots
os.makedirs('visualizations', exist_ok=True)

# ============================================================================
# 1. COST ANALYSIS - Fees Over Time
# ============================================================================
plt.figure(figsize=(14, 6))
df_daily_fees = df.groupby('Date')['Fees'].sum().reset_index()
plt.plot(df_daily_fees['Date'], df_daily_fees['Fees'], marker='o', linewidth=2, markersize=4)
plt.title('Transaction Fees Over Time', fontsize=16, fontweight='bold')
plt.xlabel('Date', fontsize=12)
plt.ylabel('Total Fees ($)', fontsize=12)
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('visualizations/1_fees_over_time.png', dpi=300, bbox_inches='tight')
plt.close()

# Fees distribution
plt.figure(figsize=(10, 6))
fees_positive = df[df['Fees'] < 0]['Fees'].abs()  # Fees are negative in the data
plt.hist(fees_positive, bins=50, edgecolor='black', alpha=0.7)
plt.title('Distribution of Transaction Fees', fontsize=16, fontweight='bold')
plt.xlabel('Fee Amount ($)', fontsize=12)
plt.ylabel('Frequency', fontsize=12)
plt.grid(True, alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig('visualizations/2_fees_distribution.png', dpi=300, bbox_inches='tight')
plt.close()

# ============================================================================
# 2. PROFITABILITY ANALYSIS
# ============================================================================
# Gross Sales vs Net Total
plt.figure(figsize=(14, 6))
df_daily = df.groupby('Date').agg({
    'Gross Sales': 'sum',
    'Net Total': 'sum',
    'Fees': 'sum'
}).reset_index()

x = range(len(df_daily))
width = 0.35
plt.bar([i - width/2 for i in x], df_daily['Gross Sales'], width, 
        label='Gross Sales', alpha=0.8, color='#2ecc71')
plt.bar([i + width/2 for i in x], df_daily['Net Total'], width, 
        label='Net Total (After Fees)', alpha=0.8, color='#3498db')
plt.title('Gross Sales vs Net Total (Daily)', fontsize=16, fontweight='bold')
plt.xlabel('Date', fontsize=12)
plt.ylabel('Amount ($)', fontsize=12)
plt.xticks(x[::5], df_daily['Date'].dt.strftime('%Y-%m-%d')[::5], rotation=45)
plt.legend(fontsize=11)
plt.grid(True, alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig('visualizations/3_gross_vs_net.png', dpi=300, bbox_inches='tight')
plt.close()

# Profitability margin
df['Profit Margin'] = (df['Net Total'] / df['Gross Sales'] * 100).replace([np.inf, -np.inf], np.nan)
df['Profit Margin'] = df['Profit Margin'].fillna(0)

plt.figure(figsize=(14, 6))
df_daily_margin = df.groupby('Date')['Profit Margin'].mean().reset_index()
plt.plot(df_daily_margin['Date'], df_daily_margin['Profit Margin'], 
         marker='o', linewidth=2, markersize=4, color='#e74c3c')
plt.title('Average Profit Margin Over Time (%)', fontsize=16, fontweight='bold')
plt.xlabel('Date', fontsize=12)
plt.ylabel('Profit Margin (%)', fontsize=12)
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('visualizations/4_profit_margin.png', dpi=300, bbox_inches='tight')
plt.close()

# Total fees impact
total_gross = df['Gross Sales'].sum()
total_net = df['Net Total'].sum()
total_fees = abs(df['Fees'].sum())

plt.figure(figsize=(10, 8))
categories = ['Gross Sales', 'Fees', 'Net Total']
values = [total_gross, -total_fees, total_net]
colors = ['#2ecc71', '#e74c3c', '#3498db']
bars = plt.bar(categories, values, color=colors, alpha=0.8, edgecolor='black', linewidth=1.5)
plt.title('Total Revenue Breakdown', fontsize=16, fontweight='bold')
plt.ylabel('Amount ($)', fontsize=12)
plt.grid(True, alpha=0.3, axis='y')

# Add value labels on bars
for bar, val in zip(bars, values):
    height = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2., height,
             f'${val:,.2f}',
             ha='center', va='bottom' if val > 0 else 'top', fontsize=11, fontweight='bold')

plt.tight_layout()
plt.savefig('visualizations/5_revenue_breakdown.png', dpi=300, bbox_inches='tight')
plt.close()

# ============================================================================
# 3. ITEM ANALYSIS
# ============================================================================
# Extract individual items from Description column
def extract_items(description):
    """Extract individual items from description string"""
    if pd.isna(description):
        return []
    
    items = []
    # Split by common delimiters
    parts = re.split(r',\s*(?=\d+\s*x\s*)|,\s*(?=[A-Z])', str(description))
    
    for part in parts:
        part = part.strip()
        # Remove quantity prefixes like "2 x" or "3 x"
        part = re.sub(r'^\d+\s*x\s*', '', part, flags=re.IGNORECASE)
        # Remove "(Regular)" suffix
        part = re.sub(r'\s*\(Regular\)\s*', '', part, flags=re.IGNORECASE)
        # Remove long descriptions after dashes
        part = re.sub(r'\s*-\s*.*$', '', part)
        part = part.strip()
        
        if part and len(part) > 2:
            items.append(part)
    
    return items if items else [description.strip()]

# Create item-level data
item_data = []
for idx, row in df.iterrows():
    items = extract_items(row['Description'])
    for item in items:
        item_data.append({
            'Date': row['Date'],
            'Item': item,
            'Gross Sales': row['Gross Sales'] / len(items) if items else row['Gross Sales'],
            'Net Total': row['Net Total'] / len(items) if items else row['Net Total'],
            'Transaction ID': row['Transaction ID']
        })

df_items = pd.DataFrame(item_data)

# Top 20 items by sales volume
top_items = df_items.groupby('Item').agg({
    'Gross Sales': 'sum',
    'Net Total': 'sum',
    'Transaction ID': 'count'
}).reset_index()
top_items.columns = ['Item', 'Total Gross Sales', 'Total Net Sales', 'Transaction Count']
top_items = top_items.sort_values('Total Gross Sales', ascending=False).head(20)

plt.figure(figsize=(14, 10))
y_pos = np.arange(len(top_items))
plt.barh(y_pos, top_items['Total Gross Sales'], alpha=0.8, color='#9b59b6', edgecolor='black')
plt.yticks(y_pos, top_items['Item'])
plt.xlabel('Total Gross Sales ($)', fontsize=12)
plt.title('Top 20 Items by Gross Sales', fontsize=16, fontweight='bold')
plt.gca().invert_yaxis()
plt.grid(True, alpha=0.3, axis='x')

# Add value labels
for i, (idx, row) in enumerate(top_items.iterrows()):
    plt.text(row['Total Gross Sales'], i, f'${row["Total Gross Sales"]:,.0f}',
             va='center', ha='left', fontsize=9)

plt.tight_layout()
plt.savefig('visualizations/6_top_items_sales.png', dpi=300, bbox_inches='tight')
plt.close()

# Top items by transaction count
top_items_count = top_items.sort_values('Transaction Count', ascending=False).head(15)

plt.figure(figsize=(12, 8))
y_pos = np.arange(len(top_items_count))
plt.barh(y_pos, top_items_count['Transaction Count'], alpha=0.8, color='#f39c12', edgecolor='black')
plt.yticks(y_pos, top_items_count['Item'])
plt.xlabel('Number of Transactions', fontsize=12)
plt.title('Top 15 Items by Transaction Frequency', fontsize=16, fontweight='bold')
plt.gca().invert_yaxis()
plt.grid(True, alpha=0.3, axis='x')

# Add value labels
for i, (idx, row) in enumerate(top_items_count.iterrows()):
    plt.text(row['Transaction Count'], i, f'{int(row["Transaction Count"])}',
             va='center', ha='left', fontsize=9)

plt.tight_layout()
plt.savefig('visualizations/7_top_items_frequency.png', dpi=300, bbox_inches='tight')
plt.close()

# ============================================================================
# 4. SALES TRENDS OVER TIME
# ============================================================================
# Daily sales trend
plt.figure(figsize=(14, 6))
df_daily_sales = df.groupby('Date').agg({
    'Gross Sales': 'sum',
    'Net Total': 'sum',
    'Transaction ID': 'count'
}).reset_index()

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

# Sales amount
ax1.plot(df_daily_sales['Date'], df_daily_sales['Gross Sales'], 
         marker='o', linewidth=2, markersize=4, label='Gross Sales', color='#2ecc71')
ax1.plot(df_daily_sales['Date'], df_daily_sales['Net Total'], 
         marker='s', linewidth=2, markersize=4, label='Net Total', color='#3498db')
ax1.set_ylabel('Sales Amount ($)', fontsize=12)
ax1.set_title('Daily Sales Trends', fontsize=16, fontweight='bold')
ax1.legend(fontsize=11)
ax1.grid(True, alpha=0.3)

# Transaction count
ax2.bar(df_daily_sales['Date'], df_daily_sales['Transaction ID'], 
        alpha=0.7, color='#e74c3c', edgecolor='black')
ax2.set_xlabel('Date', fontsize=12)
ax2.set_ylabel('Number of Transactions', fontsize=12)
ax2.set_title('Daily Transaction Count', fontsize=14, fontweight='bold')
ax2.grid(True, alpha=0.3, axis='y')

plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('visualizations/8_daily_trends.png', dpi=300, bbox_inches='tight')
plt.close()

# Hourly sales pattern
df['Hour'] = df['DateTime'].dt.hour
hourly_sales = df.groupby('Hour').agg({
    'Gross Sales': 'sum',
    'Transaction ID': 'count'
}).reset_index()

plt.figure(figsize=(14, 6))
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# Sales by hour
ax1.bar(hourly_sales['Hour'], hourly_sales['Gross Sales'], 
        alpha=0.8, color='#16a085', edgecolor='black')
ax1.set_xlabel('Hour of Day', fontsize=12)
ax1.set_ylabel('Total Sales ($)', fontsize=12)
ax1.set_title('Sales by Hour of Day', fontsize=14, fontweight='bold')
ax1.set_xticks(range(0, 24, 2))
ax1.grid(True, alpha=0.3, axis='y')

# Transactions by hour
ax2.bar(hourly_sales['Hour'], hourly_sales['Transaction ID'], 
        alpha=0.8, color='#d35400', edgecolor='black')
ax2.set_xlabel('Hour of Day', fontsize=12)
ax2.set_ylabel('Number of Transactions', fontsize=12)
ax2.set_title('Transaction Count by Hour of Day', fontsize=14, fontweight='bold')
ax2.set_xticks(range(0, 24, 2))
ax2.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('visualizations/9_hourly_patterns.png', dpi=300, bbox_inches='tight')
plt.close()

# ============================================================================
# 5. PAYMENT METHOD ANALYSIS
# ============================================================================
payment_methods = []
for idx, row in df.iterrows():
    if row['Card'] > 0:
        payment_methods.append('Card')
    elif row['Cash'] > 0:
        payment_methods.append('Cash')
    else:
        payment_methods.append('Other')

df['Payment Method'] = payment_methods
payment_summary = df.groupby('Payment Method').agg({
    'Gross Sales': 'sum',
    'Transaction ID': 'count'
}).reset_index()

plt.figure(figsize=(12, 8))
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Sales by payment method
colors_payment = ['#3498db', '#2ecc71', '#95a5a6']
ax1.pie(payment_summary['Gross Sales'], labels=payment_summary['Payment Method'], 
        autopct='%1.1f%%', startangle=90, colors=colors_payment, 
        textprops={'fontsize': 11, 'fontweight': 'bold'})
ax1.set_title('Sales Distribution by Payment Method', fontsize=14, fontweight='bold')

# Transaction count by payment method
ax2.bar(payment_summary['Payment Method'], payment_summary['Transaction ID'], 
        alpha=0.8, color=colors_payment, edgecolor='black')
ax2.set_ylabel('Number of Transactions', fontsize=12)
ax2.set_title('Transaction Count by Payment Method', fontsize=14, fontweight='bold')
ax2.grid(True, alpha=0.3, axis='y')

# Add value labels
for i, (idx, row) in enumerate(payment_summary.iterrows()):
    ax2.text(i, row['Transaction ID'], f'{int(row["Transaction ID"])}',
             ha='center', va='bottom', fontsize=11, fontweight='bold')

plt.tight_layout()
plt.savefig('visualizations/10_payment_methods.png', dpi=300, bbox_inches='tight')
plt.close()

# ============================================================================
# 6. SUMMARY STATISTICS
# ============================================================================
print("=" * 70)
print("TRANSACTION DATA SUMMARY")
print("=" * 70)
print(f"\nDate Range: {df['Date'].min().strftime('%Y-%m-%d')} to {df['Date'].max().strftime('%Y-%m-%d')}")
print(f"Total Transactions: {len(df):,}")
print(f"\nFinancial Summary:")
print(f"  Total Gross Sales: ${df['Gross Sales'].sum():,.2f}")
print(f"  Total Fees: ${abs(df['Fees'].sum()):,.2f}")
print(f"  Total Net Revenue: ${df['Net Total'].sum():,.2f}")
print(f"  Average Transaction Value: ${df['Gross Sales'].mean():.2f}")
print(f"  Average Fee per Transaction: ${abs(df['Fees'].mean()):.2f}")
print(f"\nProfitability:")
print(f"  Average Profit Margin: {df['Profit Margin'].mean():.2f}%")
print(f"  Fee Impact: {(abs(df['Fees'].sum()) / df['Gross Sales'].sum() * 100):.2f}% of gross sales")
print(f"\nTop 5 Items by Sales:")
for i, (idx, row) in enumerate(top_items.head(5).iterrows(), 1):
    print(f"  {i}. {row['Item']}: ${row['Total Gross Sales']:,.2f} ({int(row['Transaction Count'])} transactions)")

print("\n" + "=" * 70)
print(f"All visualizations saved to 'visualizations/' directory")
print("=" * 70)

