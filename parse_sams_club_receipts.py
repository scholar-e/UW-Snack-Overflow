"""
Parse Sam's Club receipts from PDF files and convert them to CSV format.
Dedicated parser with careful handling of Sam's Club receipt format.
"""

import pdfplumber
import pandas as pd
import re
from pathlib import Path
from datetime import datetime


def is_valid_item(item_name):
    """
    Check if an item name is actually a product item and not a payment method,
    total, or other non-item entry.
    
    Returns True if it's a valid item, False otherwise.
    """
    if not item_name or len(item_name.strip()) < 2:
        return False
    
    item_upper = item_name.upper().strip()
    
    # Non-item keywords to filter out
    non_item_keywords = [
        'AMOUNT', 'TOTAL', 'SUBTOTAL', 'TAX', 'BALANCE', 'DUE',
        'CASH', 'CARD', 'CREDIT', 'DEBIT', 'PAYMENT', 'PAID',
        'CHANGE', 'REFUND', 'DISCOUNT', 'COUPON', 'REWARD',
        'RECEIPT', 'INVOICE', 'DATE', 'TIME', 'STORE', 'WAREHOUSE',
        'MEMBERSHIP', 'THANK', 'YOU', 'VISIT', 'AGAIN',
        'ITEM', 'DESCRIPTION', 'QTY', 'QUANTITY', 'PRICE',
        'VISA', 'MASTERCARD', 'AMEX', 'DISCOVER', 'CHECK',
        'GIFT', 'CARD', 'BALANCE', 'REMAINING', 'APPROVED',
        'PURCHASE', 'CHIP', 'READ', 'INSTANT', 'SAVINGS',
        'SHIPPING', 'SALES', 'ORDER', 'AUTHORIZATION', 'PENDING',
        'CHARGE', 'FUNDS', 'AVAILABLE', 'CREDIT CARDS'
    ]
    
    # Check if item name is just a non-item keyword
    if item_upper in non_item_keywords:
        return False
    
    # Check if item name starts with non-item keywords followed by colon
    if any(item_upper.startswith(keyword + ':') or item_upper.startswith(keyword + ' ') 
           for keyword in non_item_keywords):
        return False
    
    # Check if it's just a number or mostly numbers/symbols (likely not an item)
    if re.match(r'^[\d\s#,\-*$]+$', item_name):
        return False
    
    # Check if it's just symbols and numbers (like "*4943 $")
    if re.match(r'^[*#$]+\s*\d+\s*[*#$]*$', item_name):
        return False
    
    # Check if it looks like a payment method line
    if re.match(r'^(CASH|CARD|CREDIT|DEBIT|VISA|MASTERCARD)', item_upper):
        return False
    
    # Check if it's a discount line (contains / and ends with -)
    if '/' in item_name and item_name.strip().endswith('-'):
        return False
    
    return True


def parse_sams_club_line(line):
    """
    Parse a single line from a Sam's Club receipt.
    Format: "Item Name Qty X $Price"
    Example: "Red Bull Energy Sugar-Free 8.4 fl. oz., 24 pk. Qty 1 $34.98"
    
    Returns dict with item info or None if not an item line.
    """
    line = line.strip()
    if not line:
        return None
    
    # Skip discount and non-item lines
    if '/' in line and line.strip().endswith('-'):
        return None
    
    if any(skip in line.upper() for skip in ['SUBTOTAL', 'TOTAL', 'TAX', 'AMOUNT:', 
                                              'CASH', 'CHANGE', 'APPROVED', 'PURCHASE',
                                              'SHIPPING', 'SALES', 'ORDER', 'CREDIT CARDS']):
        return None
    
    # Skip address lines
    if re.match(r'^\d+\s+[A-Z]', line) and ('BLVD' in line or 'ST' in line or 'AVE' in line or 'RD' in line):
        return None
    
    # Pattern for Sam's Club items: "Item Name Qty X $Price"
    # Look for "Qty" followed by number, then "$" and price
    qty_price_pattern = r'Qty\s+(\d+)\s+\$(\d+\.\d{2})\s*$'
    match = re.search(qty_price_pattern, line, re.IGNORECASE)
    
    if match:
        quantity = int(match.group(1))
        price = float(match.group(2))
        
        # Extract item name (everything before "Qty")
        item_name = line[:match.start()].strip()
        
        # Clean item name
        item_name = re.sub(r'\s+', ' ', item_name)
        
        # Remove trailing "Qty" if present (shouldn't be, but just in case)
        item_name = re.sub(r'\s+Qty\s*$', '', item_name, flags=re.IGNORECASE).strip()
        
        # Check if item name is valid
        if item_name and is_valid_item(item_name) and price > 0:
            return {
                'item_code': '',  # Sam's Club receipts don't typically have item codes
                'item_name': item_name,
                'quantity': quantity,
                'unit_price': price / quantity if quantity > 1 else price,
                'total_price': price
            }
    
    # Alternative pattern: Item name with price at end (no explicit Qty)
    # Format: "Item Name $Price"
    price_only_pattern = r'\$(\d+\.\d{2})\s*$'
    match = re.search(price_only_pattern, line)
    
    if match:
        price = float(match.group(1))
        item_name = line[:match.start()].strip()
        
        # Clean item name
        item_name = re.sub(r'\s+', ' ', item_name)
        
        # Look for quantity indicators in the item name
        quantity = 1
        
        # Check for "Qty X" pattern anywhere in the name
        qty_match = re.search(r'Qty\s+(\d+)', item_name, re.IGNORECASE)
        if qty_match:
            quantity = int(qty_match.group(1))
            # Remove the Qty part from item name
            item_name = re.sub(r'\s*Qty\s+\d+\s*', ' ', item_name, flags=re.IGNORECASE).strip()
            item_name = re.sub(r'\s+', ' ', item_name)
        
        # Check for pack size indicators that might indicate quantity
        # e.g., "24 pk" means 24 pieces, but that's the pack size, not quantity purchased
        # We'll be conservative and only use explicit "Qty X" quantities
        
        if item_name and is_valid_item(item_name) and price > 0:
            return {
                'item_code': '',
                'item_name': item_name,
                'quantity': quantity,
                'unit_price': price / quantity if quantity > 1 else price,
                'total_price': price
            }
    
    return None


def parse_sams_club_receipt(pdf_path):
    """
    Parse a Sam's Club receipt PDF and extract item information.
    
    Returns a list of dictionaries with receipt data.
    """
    items = []
    receipt_data = {
        'store': "Sam's Club",
        'date': None,
        'receipt_number': None,
        'total': None,
        'items': []
    }
    
    try:
        # Extract date from filename first
        filename = Path(pdf_path).stem
        date_match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', filename)
        if date_match:
            month, day, year = date_match.groups()
            year = '20' + year if len(year) == 2 else year
            receipt_data['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        with pdfplumber.open(pdf_path) as pdf:
            # Extract all text
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
            
            lines = full_text.split('\n')
            
            # Extract receipt number (Order number)
            for line in lines:
                if 'ORDER' in line.upper() or 'RECEIPT' in line.upper() or 'INVOICE' in line.upper() or 'INV#' in line.upper():
                    numbers = re.findall(r'\d{8,}', line)  # Order numbers are typically long
                    if numbers:
                        receipt_data['receipt_number'] = numbers[0]
                        break
            
            # Extract date from receipt if not found in filename
            if not receipt_data['date']:
                for line in lines:
                    date_match = re.search(r'(\w+)\s+(\d{1,2}),\s+(\d{4})', line)
                    if date_match:
                        month_name, day, year = date_match.groups()
                        month_map = {
                            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                        }
                        month = month_map.get(month_name[:3], '01')
                        receipt_data['date'] = f"{year}-{month}-{day.zfill(2)}"
                        break
            
            # Parse each line, handling multi-line items
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Skip header lines
                if any(skip in line.upper() for skip in ["SAM'S", 'CLUB', 'MEMBER', 
                                                          'HTTP', 'WWW', 'SHIPPING ITEMS',
                                                          'ORDER', 'HUGH', 'GRAMELSPACHER',
                                                          'NE', 'BLVD', 'SEATTLE', 'WA']):
                    i += 1
                    continue
                
                # Try to parse as Sam's Club item
                item_info = parse_sams_club_line(line)
                
                if item_info:
                    # Check if next line might be continuation of item name
                    # (Some items have descriptions split across lines)
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # If next line doesn't look like a new item and is short, might be continuation
                        if next_line and len(next_line) < 50 and \
                           not re.search(r'Qty\s+\d+\s+\$', next_line, re.IGNORECASE) and \
                           not re.search(r'\$\d+\.\d{2}', next_line) and \
                           not any(skip in next_line.upper() for skip in ['TOTAL', 'SUBTOTAL', 'TAX', 'CASH', 'SHIPPING']):
                            # Might be part of item name
                            item_info['item_name'] = item_info['item_name'] + ' ' + next_line
                            item_info['item_name'] = re.sub(r'\s+', ' ', item_info['item_name']).strip()
                            i += 1  # Skip the continuation line
                    
                    # Only add if we have a valid item name
                    if item_info['item_name'] and is_valid_item(item_info['item_name']):
                        items.append({
                            'item_code': item_info.get('item_code', ''),
                            'item_name': item_info['item_name'],
                            'quantity': item_info['quantity'],
                            'unit_price': item_info['unit_price'],
                            'total_price': item_info['total_price'],
                            'store': "Sam's Club",
                            'receipt_date': receipt_data['date'],
                            'receipt_number': receipt_data['receipt_number']
                        })
                
                i += 1
    
    except Exception as e:
        print(f"Error parsing Sam's Club receipt {pdf_path}: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def parse_receipt_directory(directory_path):
    """
    Parse all Sam's Club receipt PDFs in a directory and combine them into a single DataFrame.
    
    Args:
        directory_path: Path to directory containing receipt PDFs
    
    Returns:
        pandas DataFrame with all receipt items
    """
    all_items = []
    directory = Path(directory_path)
    
    # Find all Sam's Club PDF files
    pdf_files = [f for f in directory.glob('*.pdf') if f.name.startswith('SC')]
    
    if not pdf_files:
        print(f"No Sam's Club PDF files found in {directory_path}")
        return pd.DataFrame()
    
    print(f"Found {len(pdf_files)} Sam's Club PDF files to process...")
    
    for pdf_file in pdf_files:
        filename = pdf_file.name
        print(f"Processing: {filename}")
        
        items = parse_sams_club_receipt(pdf_file)
        print(f"  Extracted {len(items)} items")
        all_items.extend(items)
    
    if not all_items:
        print("No items extracted from receipts.")
        return pd.DataFrame()
    
    # Create DataFrame
    df = pd.DataFrame(all_items)
    
    return df


def main():
    """
    Main function to parse Sam's Club receipts and save to CSV.
    """
    # Default receipt directory
    receipt_dir = Path('Receipts-20251113T013859Z-1-001/Receipts')
    
    if not receipt_dir.exists():
        print(f"Receipt directory not found: {receipt_dir}")
        print("Please specify the correct path to your receipts directory.")
        return
    
    # Parse all Sam's Club receipts
    print("=" * 70)
    print("PARSING SAM'S CLUB RECEIPTS")
    print("=" * 70)
    df = parse_receipt_directory(receipt_dir)
    
    if df.empty:
        print("No data extracted. Exiting.")
        return
    
    # Helper function to format DataFrame (no item_code for Sam's Club)
    def format_dataframe(df_subset):
        return pd.DataFrame({
            'item': df_subset['item_name'],
            'unit_number': df_subset['quantity'],
            'date': df_subset['receipt_date'],
            'cost': df_subset['total_price']
        })
    
    # Format and save
    df_formatted = format_dataframe(df)
    output_file = Path('parsed_receipts/receipts_sams_club.csv')
    output_file.parent.mkdir(exist_ok=True)
    df_formatted.to_csv(output_file, index=False)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total items extracted: {len(df_formatted)}")
    print(f"Total receipts processed: {df_formatted['date'].nunique()}")
    print(f"Total cost: ${df_formatted['cost'].sum():,.2f}")
    print(f"Average item cost: ${df_formatted['cost'].mean():.2f}")
    print(f"Items with quantity > 1: {len(df_formatted[df_formatted['unit_number'] > 1])}")
    print(f"\nData saved to: {output_file}")
    print("=" * 70)
    
    # Show sample of data
    print("\nSample of extracted data:")
    print(df_formatted.head(15).to_string())
    
    # Show items with quantities > 1
    qty_items = df_formatted[df_formatted['unit_number'] > 1]
    if len(qty_items) > 0:
        print(f"\nItems with quantity > 1 ({len(qty_items)} items):")
        print(qty_items[['item', 'unit_number', 'cost']].head(10).to_string())


if __name__ == '__main__':
    main()

