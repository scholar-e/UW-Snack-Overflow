"""
Collate and aggregate Costco receipt items.
Uses item codes to scrape proper item names from Costco website,
then estimates quantities and creates a collated CSV similar to Sam's Club format.
"""

import pandas as pd
import re
import requests
from pathlib import Path
from time import sleep
from bs4 import BeautifulSoup


def scrape_costco_item_info(item_code, fallback_name=None):
    """
    Scrape item name and price from Costco website using item code.
    URL format: https://www.costco.com/s?keyword=[ITEM_CODE]
    
    Args:
        item_code: Costco item code
        fallback_name: Name to return if scraping fails
    
    Returns tuple of (item_name, unit_price) or (fallback_name, None) if not found.
    """
    if not item_code or pd.isna(item_code) or str(item_code).strip() == '':
        return fallback_name
    
    url = f"https://www.costco.com/s?keyword={item_code}"
    
    try:
        # Add headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try to find the product name in various possible locations
        product_name = None
        
        # Method 1: Try h1 tag (product detail page)
        h1 = soup.find('h1')
        if h1:
            product_name = h1.get_text(strip=True)
            if product_name and len(product_name) > 3:
                return product_name
        
        # Method 2: Try product title in search results
        product_titles = soup.find_all(class_=re.compile(r'product-title|product-name|description', re.I))
        for title_elem in product_titles:
            text = title_elem.get_text(strip=True)
            if text and len(text) > 3 and 'costco' not in text.lower():
                product_name = text
                break
        
        # Method 3: Try product links
        if not product_name:
            product_links = soup.find_all('a', href=re.compile(r'/product\.|/p\.|/.*product'))
            for link in product_links[:3]:  # Check first 3 links
                text = link.get_text(strip=True)
                if text and len(text) > 3 and len(text) < 200:
                    product_name = text
                    break
        
        # Method 4: Try meta title and clean it
        if not product_name:
            meta_title = soup.find('title')
            if meta_title:
                title_text = meta_title.get_text(strip=True)
                # Remove "Costco" and other common prefixes/suffixes
                product_name = re.sub(r'^.*?Costco\s*[-|]?\s*', '', title_text, flags=re.I)
                product_name = re.sub(r'\s*[-|]\s*Costco.*$', '', product_name, flags=re.I)
                product_name = re.sub(r'\s*[-|]\s*Shop.*$', '', product_name, flags=re.I)
                product_name = product_name.strip()
        
        # Try to extract price
        unit_price = None
        
        # Method 1: Look for price in various formats
        price_patterns = [
            r'\$(\d+\.?\d*)',  # $XX.XX
            r'(\d+\.?\d*)\s*USD',  # XX.XX USD
            r'price[:\s]*\$?(\d+\.?\d*)',  # price: $XX.XX
        ]
        
        # Look for price in text content
        price_text = soup.get_text()
        for pattern in price_patterns:
            matches = re.findall(pattern, price_text, re.IGNORECASE)
            if matches:
                # Try to find the most reasonable price (not too high, not too low)
                prices = [float(m) for m in matches if float(m) > 0.01 and float(m) < 10000]
                if prices:
                    # Use median price as it's likely the product price
                    prices.sort()
                    unit_price = prices[len(prices)//2]
                    break
        
        # Method 2: Look for price in specific elements
        if not unit_price:
            price_elements = soup.find_all(class_=re.compile(r'price|cost|amount', re.I))
            for elem in price_elements:
                text = elem.get_text(strip=True)
                price_match = re.search(r'\$?(\d+\.?\d{2})', text)
                if price_match:
                    price_val = float(price_match.group(1))
                    if 0.01 < price_val < 10000:  # Reasonable price range
                        unit_price = price_val
                        break
        
        # Method 3: Look in meta tags
        if not unit_price:
            price_meta = soup.find('meta', property=re.compile(r'price', re.I))
            if price_meta:
                price_content = price_meta.get('content') or price_meta.get('value')
                if price_content:
                    price_match = re.search(r'(\d+\.?\d{2})', str(price_content))
                    if price_match:
                        unit_price = float(price_match.group(1))
        
        if product_name and len(product_name) > 3:
            return (product_name, unit_price)
        
        return (fallback_name, None)
        
    except requests.exceptions.Timeout:
        print(f"  Timeout for {item_code}")
        return (fallback_name, None)
    except requests.exceptions.RequestException as e:
        print(f"  Request error for {item_code}: {str(e)[:50]}")
        return (fallback_name, None)
    except Exception as e:
        print(f"  Error scraping {item_code}: {str(e)[:50]}")
        return (fallback_name, None)


def estimate_quantity_from_price(total_cost, estimated_unit_price):
    """
    Estimate quantity by dividing total cost by estimated unit price.
    Returns integer quantity.
    """
    if estimated_unit_price <= 0:
        return 1
    
    estimated_qty = total_cost / estimated_unit_price
    
    # Round to nearest integer, but at least 1
    return max(1, round(estimated_qty))


def normalize_item_name(item_name):
    """
    Normalize item name for comparison (remove extra spaces, etc.)
    """
    if not item_name:
        return ""
    
    normalized = item_name
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def collate_costco_items(csv_path, scrape_names=True):
    """
    Collate identical items from Costco receipts.
    
    Args:
        csv_path: Path to the Costco receipts CSV
        scrape_names: Whether to scrape item names from Costco website
    
    Returns:
        DataFrame with aggregated items
    """
    # Read the CSV
    df = pd.read_csv(csv_path)
    
    print(f"Loaded {len(df)} items from {csv_path}")
    
    # Group by item_code first to aggregate costs
    grouped = df.groupby('item_code').agg({
        'item': 'first',  # Keep first item name
        'cost': 'sum',  # Sum all costs for this item code
        'unit_number': 'sum',  # Sum unit numbers
        'date': 'first'  # Keep first date
    }).reset_index()
    
    print(f"Found {len(grouped)} unique item codes")
    
    # Scrape proper item names if requested
    if scrape_names:
        print("\nScraping item names from Costco website...")
        print("(This may take a while - scraping with delays to be respectful...)")
        print("(Items not found will use existing names from receipts)\n")
        
        scraped_info = {}  # {item_code: (name, unit_price)}
        unique_codes = grouped['item_code'].dropna().unique()
        total_codes = len(unique_codes)
        
        for i, item_code in enumerate(unique_codes, 1):
            item_code_str = str(item_code).strip()
            if item_code_str and item_code_str != 'nan' and item_code_str != '':
                # Get fallback name
                fallback = grouped[grouped['item_code'] == item_code]['item'].iloc[0] if len(grouped[grouped['item_code'] == item_code]) > 0 else None
                
                print(f"  [{i}/{total_codes}] Scraping {item_code_str}...", end=' ')
                item_name, unit_price = scrape_costco_item_info(item_code_str, fallback_name=fallback)
                if item_name and item_name != fallback:
                    scraped_info[item_code_str] = (item_name, unit_price)
                    price_str = f" (${unit_price:.2f})" if unit_price else " (no price)"
                    print(f"✓ Found: {item_name[:50]}{price_str}")
                else:
                    print("✗ Using receipt name")
                
                # Be polite - add a delay between requests
                sleep(1)
        
        # Update item names and store prices for quantity calculation
        grouped['scraped_price'] = None
        for idx, row in grouped.iterrows():
            item_code = str(row['item_code']).strip()
            if item_code in scraped_info:
                item_name, unit_price = scraped_info[item_code]
                grouped.at[idx, 'item'] = item_name
                if unit_price:
                    grouped.at[idx, 'scraped_price'] = unit_price
    
    # Normalize item names for further grouping
    grouped['normalized_item'] = grouped['item'].apply(normalize_item_name)
    
    # Group by normalized item name to combine items with same name but different codes
    # For scraped_price, use the first non-null value (or average if multiple)
    aggregated = grouped.groupby('normalized_item').agg({
        'item': 'first',  # Keep the first item name
        'cost': 'sum',  # Sum all costs
        'unit_number': 'sum',  # Sum unit numbers
        'scraped_price': lambda x: x.dropna().iloc[0] if len(x.dropna()) > 0 else None,  # First non-null price
    }).reset_index(drop=True)
    
    # Calculate quantities using scraped prices or rough division
    aggregated['quantity'] = aggregated['unit_number']  # Start with unit_number
    
    # If we have scraped prices, use those to calculate quantity
    if 'scraped_price' in aggregated.columns:
        for idx, row in aggregated.iterrows():
            cost = row['cost']
            scraped_price = row.get('scraped_price')
            
            if scraped_price and pd.notna(scraped_price) and scraped_price > 0:
                # Calculate quantity based on scraped price
                calculated_qty = round(cost / scraped_price)
                # Ensure at least 1
                aggregated.at[idx, 'quantity'] = max(1, calculated_qty)
    
    # For items without scraped prices, use rough division
    # Calculate median cost per unit to use as baseline
    median_cost_per_unit = (aggregated['cost'] / aggregated['unit_number']).median()
    
    # For items with high cost relative to unit_number, estimate quantity
    for idx, row in aggregated.iterrows():
        cost = row['cost']
        unit_num = row['unit_number']
        scraped_price = row.get('scraped_price') if 'scraped_price' in row else None
        
        # Skip if we already calculated from scraped price
        if scraped_price and pd.notna(scraped_price) and scraped_price > 0:
            continue
        
        cost_per_unit = cost / unit_num if unit_num > 0 else cost
        
        # If cost per unit is significantly higher than median, likely more items
        # Rough heuristic: if cost_per_unit > 1.5 * median, estimate more units
        if cost_per_unit > median_cost_per_unit * 1.5:
            # Estimate quantity: divide total cost by estimated unit price
            estimated_unit_price = median_cost_per_unit
            estimated_qty = max(unit_num, round(cost / estimated_unit_price))
            aggregated.at[idx, 'quantity'] = estimated_qty
        # If cost per unit is very low, might be bulk pricing (keep unit_number)
    
    # Rename columns
    aggregated = aggregated[['item', 'quantity', 'cost']].copy()
    aggregated.columns = ['item', 'quantity', 'total_cost']
    
    # Sort by total cost descending
    aggregated = aggregated.sort_values('total_cost', ascending=False)
    
    return aggregated


def main():
    """
    Main function to collate Costco items.
    """
    csv_path = Path('parsed_receipts/receipts_costco.csv')
    
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        return
    
    print("=" * 70)
    print("COLLATING COSTCO ITEMS")
    print("=" * 70)
    
    # Collate items (set scrape_names=False to skip web scraping for faster testing)
    # Set scrape_names=True to scrape proper names from Costco website (takes longer)
    import sys
    scrape_names = '--scrape' in sys.argv or '--with-scraping' in sys.argv
    aggregated_df = collate_costco_items(csv_path, scrape_names=scrape_names)
    
    # Save to CSV
    output_file = Path('parsed_receipts/receipts_costco_collated.csv')
    aggregated_df.to_csv(output_file, index=False)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total unique items: {len(aggregated_df)}")
    print(f"Total quantity (all items): {aggregated_df['quantity'].sum():,}")
    print(f"Total cost: ${aggregated_df['total_cost'].sum():,.2f}")
    print(f"Average cost per item: ${aggregated_df['total_cost'].mean():.2f}")
    print(f"\nData saved to: {output_file}")
    print("=" * 70)
    
    # Show top items by cost
    print("\nTop 20 items by total cost:")
    print(aggregated_df[['item', 'quantity', 'total_cost']].head(20).to_string())
    
    # Show top items by quantity
    print("\n\nTop 20 items by total quantity:")
    top_qty = aggregated_df.sort_values('quantity', ascending=False)
    print(top_qty[['item', 'quantity', 'total_cost']].head(20).to_string())


if __name__ == '__main__':
    main()

