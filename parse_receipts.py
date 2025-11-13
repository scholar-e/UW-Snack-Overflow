"""
Parse Costco and Sam's Club receipts from PDF files and convert them to CSV format.
"""

import pdfplumber
import pandas as pd
import re
import os
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
        'PURCHASE', 'CHIP', 'READ', 'INSTANT', 'SAVINGS'
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


def parse_costco_line(line):
    """
    Parse a single line from a Costco receipt.
    Format: E CODE DESCRIPTION PRICE FLAG
    or: E CODE PRICE FLAG (no description, description on adjacent lines)
    or: CODE /CODE DISCOUNT-
    
    Returns dict with item info or None if not an item line.
    """
    line = line.strip()
    if not line:
        return None
    
    # Skip discount lines (format: CODE /CODE AMOUNT-)
    if '/' in line and line.strip().endswith('-'):
        return None
    
    # Skip lines that are clearly not items
    if any(skip in line.upper() for skip in ['SUBTOTAL', 'TOTAL', 'TAX', 'AMOUNT:', 
                                              'CASH', 'CHANGE', 'APPROVED', 'PURCHASE',
                                              'CHIP', 'READ', 'MEMBER', 'ORDERS', 'PURCHASES']):
        return None
    
    # Pattern 1: E CODE DESCRIPTION PRICE [FLAG]
    # Example: "E 782796 ***KSWTR40PK 11.97 Y"
    costco_pattern = r'^E\s+(\d+)\s+(.+?)\s+(\d+\.\d{2})\s*([YN]?)$'
    match = re.match(costco_pattern, line)
    
    if match:
        code, description, price_str, flag = match.groups()
        price = float(price_str)
        
        # Clean description
        description = description.strip()
        description = re.sub(r'\s+', ' ', description)
        
        # Look for quantity indicators in description (e.g., "2 x ITEM" or "2x ITEM")
        quantity = 1
        qty_match = re.search(r'^(\d+)\s*x\s+', description, re.IGNORECASE)
        if qty_match:
            quantity = int(qty_match.group(1))
            description = re.sub(r'^\d+\s*x\s+', '', description, flags=re.IGNORECASE).strip()
        
        # Check for pack size indicators that might indicate quantity
        # e.g., "6PK" might mean 6 units, but could also be "6 pack" (1 unit)
        # We'll be conservative and only extract explicit "2 x" style quantities
        
        if description:  # Allow items without description validation here, will check later
            return {
                'item_code': code,
                'item_name': description,
                'quantity': quantity,
                'unit_price': price / quantity if quantity > 1 else price,
                'total_price': price
            }
    
    # Pattern 2: E CODE PRICE FLAG (no description on this line)
    # Example: "E 1377067 44.97 N"
    code_only_pattern = r'^E\s+(\d+)\s+(\d+\.\d{2})\s*([YN]?)$'
    match = re.match(code_only_pattern, line)
    
    if match:
        code, price_str, flag = match.groups()
        price = float(price_str)
        
        # Return item with empty description - caller will look for description on adjacent lines
        return {
            'item_code': code,
            'item_name': '',  # Will be filled by caller
            'quantity': 1,
            'unit_price': price,
            'total_price': price
        }
    
    return None


def parse_costco_receipt(pdf_path):
    """
    Parse a Costco receipt PDF and extract item information.
    
    Returns a list of dictionaries with receipt data.
    """
    items = []
    receipt_data = {
        'store': 'Costco',
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
            
            # Extract receipt number
            for line in lines:
                if 'RECEIPT' in line.upper() or 'INVOICE' in line.upper():
                    numbers = re.findall(r'\d+', line)
                    if numbers:
                        receipt_data['receipt_number'] = numbers[0]
                        break
            
            # Parse each line, handling multi-line items
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Skip header lines
                if any(skip in line.upper() for skip in ['COSTCO', 'WAREHOUSE', 'MEMBER', 
                                                          'ORDERS', 'PURCHASES', 'LYNNWOOD',
                                                          'HIGHWAY', 'HTTP', 'WWW']):
                    i += 1
                    continue
                
                # Try to parse as Costco item
                item_info = parse_costco_line(line)
                
                if item_info:
                    # Check if this is an item with code but no description (format: E CODE PRICE FLAG)
                    # Look backwards and forwards for description parts
                    code_only_pattern = r'^E\s+(\d+)\s+(\d+\.\d{2})\s*([YN]?)$'
                    if re.match(code_only_pattern, line):
                        # Item has no description, look for it on adjacent lines
                        description_parts = []
                        
                        # Look backwards (up to 2 lines)
                        for j in range(max(0, i-2), i):
                            prev_line = lines[j].strip()
                            if prev_line and not prev_line.startswith('E ') and \
                               not re.match(r'^\d+\.\d{2}', prev_line) and \
                               not ('/' in prev_line and prev_line.endswith('-')) and \
                               not any(skip in prev_line.upper() for skip in ['TOTAL', 'SUBTOTAL', 'TAX', 'CASH', 'MEMBER']):
                                description_parts.insert(0, prev_line)
                        
                        # Look forwards (up to 2 lines)
                        for j in range(i+1, min(len(lines), i+3)):
                            next_line = lines[j].strip()
                            if next_line and not next_line.startswith('E ') and \
                               not re.match(r'^\d+\.\d{2}', next_line) and \
                               not ('/' in next_line and next_line.endswith('-')) and \
                               not any(skip in next_line.upper() for skip in ['TOTAL', 'SUBTOTAL', 'TAX', 'CASH', 'MEMBER']):
                                description_parts.append(next_line)
                                i = j  # Skip this line on next iteration
                                break
                        
                        if description_parts:
                            item_info['item_name'] = ' '.join(description_parts).strip()
                            item_info['item_name'] = re.sub(r'\s+', ' ', item_info['item_name'])
                    
                    # Only add if we have a valid item name
                    if item_info['item_name'] and is_valid_item(item_info['item_name']):
                        items.append({
                            'item_code': item_info.get('item_code', ''),
                            'item_name': item_info['item_name'],
                            'quantity': item_info['quantity'],
                            'unit_price': item_info['unit_price'],
                            'total_price': item_info['total_price'],
                            'store': 'Costco',
                            'receipt_date': receipt_data['date'],
                            'receipt_number': receipt_data['receipt_number']
                        })
                
                i += 1
    
    except Exception as e:
        print(f"Error parsing Costco receipt {pdf_path}: {e}")
        import traceback
        traceback.print_exc()
    
    return items


def parse_sams_club_line(line):
    """
    Parse a single line from a Sam's Club receipt.
    """
    line = line.strip()
    if not line:
        return None
    
    # Skip discount and non-item lines
    if '/' in line and line.strip().endswith('-'):
        return None
    
    if any(skip in line.upper() for skip in ['SUBTOTAL', 'TOTAL', 'TAX', 'AMOUNT:', 
                                              'CASH', 'CHANGE', 'APPROVED', 'PURCHASE']):
        return None
    
    # Sam's Club format might be different - need to check actual format
    # For now, look for price at end of line
    price_match = re.search(r'(\d+\.\d{2})\s*$', line)
    if price_match:
        price = float(price_match.group(1))
        item_text = line[:price_match.start()].strip()
        
        # Clean item text
        item_text = re.sub(r'\s+', ' ', item_text)
        
        # Look for item code (might be at start)
        item_code = ''
        code_match = re.search(r'^(\d+)\s+', item_text)
        if code_match:
            item_code = code_match.group(1)
            item_text = re.sub(r'^\d+\s+', '', item_text).strip()
        
        # Look for quantity
        quantity = 1
        qty_match = re.search(r'^(\d+)\s*x\s+', item_text, re.IGNORECASE)
        if qty_match:
            quantity = int(qty_match.group(1))
            item_text = re.sub(r'^\d+\s*x\s+', '', item_text, flags=re.IGNORECASE).strip()
        
        if is_valid_item(item_text) and price > 0:
            return {
                'item_code': item_code,
                'item_name': item_text,
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
            
            # Extract receipt number
            for line in lines:
                if 'RECEIPT' in line.upper() or 'INVOICE' in line.upper() or 'INV#' in line.upper():
                    numbers = re.findall(r'\d+', line)
                    if numbers:
                        receipt_data['receipt_number'] = numbers[0]
                        break
            
            # Parse each line
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Skip header lines
                if any(skip in line.upper() for skip in ["SAM'S", 'CLUB', 'MEMBER', 
                                                          'HTTP', 'WWW']):
                    i += 1
                    continue
                
                # Try to parse as Sam's Club item
                item_info = parse_sams_club_line(line)
                
                if item_info:
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
    Parse all receipt PDFs in a directory and combine them into a single DataFrame.
    
    Args:
        directory_path: Path to directory containing receipt PDFs
    
    Returns:
        pandas DataFrame with all receipt items
    """
    all_items = []
    directory = Path(directory_path)
    
    # Find all PDF files
    pdf_files = list(directory.glob('*.pdf'))
    
    if not pdf_files:
        print(f"No PDF files found in {directory_path}")
        return pd.DataFrame()
    
    print(f"Found {len(pdf_files)} PDF files to process...")
    
    for pdf_file in pdf_files:
        filename = pdf_file.name
        print(f"Processing: {filename}")
        
        if filename.startswith('Costco'):
            items = parse_costco_receipt(pdf_file)
            print(f"  Extracted {len(items)} items")
            all_items.extend(items)
        elif filename.startswith('SC'):
            items = parse_sams_club_receipt(pdf_file)
            print(f"  Extracted {len(items)} items")
            all_items.extend(items)
        else:
            print(f"  Unknown receipt type for {filename}, skipping...")
    
    if not all_items:
        print("No items extracted from receipts.")
        return pd.DataFrame()
    
    # Create DataFrame
    df = pd.DataFrame(all_items)
    
    return df


def main():
    """
    Main function to parse receipts and save to CSV.
    """
    # Default receipt directory
    receipt_dir = Path('Receipts-20251113T013859Z-1-001/Receipts')
    
    if not receipt_dir.exists():
        print(f"Receipt directory not found: {receipt_dir}")
        print("Please specify the correct path to your receipts directory.")
        return
    
    # Parse all receipts
    print("=" * 70)
    print("PARSING RECEIPTS")
    print("=" * 70)
    df = parse_receipt_directory(receipt_dir)
    
    if df.empty:
        print("No data extracted. Exiting.")
        return
    
    # Helper function to format DataFrame
    def format_dataframe(df_subset):
        item_codes = df_subset.get('item_code', pd.Series([''] * len(df_subset)))
        if item_codes.dtype == 'object':
            item_codes = item_codes.fillna('').astype(str)
        else:
            item_codes = item_codes.fillna('').astype(str).str.replace(r'\.0$', '', regex=True)
        
        return pd.DataFrame({
            'item_code': item_codes,
            'item': df_subset['item_name'],
            'unit_number': df_subset['quantity'],
            'date': df_subset['receipt_date'],
            'cost': df_subset['total_price']
        })
    
    # Separate by store
    costco_df = df[df['store'] == 'Costco'].copy()
    sams_club_df = df[df['store'] == "Sam's Club"].copy()
    
    # Format and save Costco receipts
    if not costco_df.empty:
        costco_formatted = format_dataframe(costco_df)
        costco_file = Path('parsed_receipts/receipts_costco.csv')
        costco_file.parent.mkdir(exist_ok=True)
        costco_formatted.to_csv(costco_file, index=False)
        print("\n" + "=" * 70)
        print("COSTCO RECEIPTS")
        print("=" * 70)
        print(f"Total items: {len(costco_formatted)}")
        print(f"Total receipts: {costco_formatted['date'].nunique()}")
        print(f"Total cost: ${costco_formatted['cost'].sum():,.2f}")
        print(f"Average item cost: ${costco_formatted['cost'].mean():.2f}")
        print(f"Items with quantity > 1: {len(costco_formatted[costco_formatted['unit_number'] > 1])}")
        print(f"Data saved to: {costco_file}")
    
    # Format and save Sam's Club receipts
    if not sams_club_df.empty:
        sams_club_formatted = format_dataframe(sams_club_df)
        sams_club_file = Path('parsed_receipts/receipts_sams_club.csv')
        sams_club_file.parent.mkdir(exist_ok=True)
        sams_club_formatted.to_csv(sams_club_file, index=False)
        print("\n" + "=" * 70)
        print("SAM'S CLUB RECEIPTS")
        print("=" * 70)
        print(f"Total items: {len(sams_club_formatted)}")
        print(f"Total receipts: {sams_club_formatted['date'].nunique()}")
        print(f"Total cost: ${sams_club_formatted['cost'].sum():,.2f}")
        print(f"Average item cost: ${sams_club_formatted['cost'].mean():.2f}")
        print(f"Items with quantity > 1: {len(sams_club_formatted[sams_club_formatted['unit_number'] > 1])}")
        print(f"Data saved to: {sams_club_file}")
    
    # Overall summary
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)
    print(f"Total items extracted: {len(df)}")
    print(f"Total receipts processed: {df['receipt_date'].nunique()}")
    print(f"Costco items: {len(costco_df) if not costco_df.empty else 0}")
    print(f"Sam's Club items: {len(sams_club_df) if not sams_club_df.empty else 0}")
    print("=" * 70)
    
    # Show samples
    if not costco_df.empty:
        print("\nSample Costco items:")
        print(format_dataframe(costco_df).head(10).to_string())
    
    if not sams_club_df.empty:
        print("\nSample Sam's Club items:")
        print(format_dataframe(sams_club_df).head(10).to_string())


if __name__ == '__main__':
    main()
