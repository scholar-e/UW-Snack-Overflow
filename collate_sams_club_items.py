"""
Collate and aggregate Sam's Club receipt items.
Combines identical items and calculates total quantities using pack size indicators (ct, pk).
"""

import pandas as pd
import re
from pathlib import Path


def extract_pack_size(item_name):
    """
    Extract pack size from item name.
    Looks for patterns like "24 ct", "18 pk", "12 count", etc.
    
    Returns the pack size as an integer, or 1 if not found.
    """
    if not item_name:
        return 1
    
    # Pattern for pack size: number followed by "ct", "pk", "count", "pieces", etc.
    patterns = [
        r'(\d+)\s*ct\b',  # "24 ct"
        r'(\d+)\s*pk\b',  # "18 pk"
        r'(\d+)\s*count\b',  # "12 count"
        r'(\d+)\s*pieces?\b',  # "30 pieces"
        r'(\d+)\s*pack\b',  # "10 pack"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, item_name, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    # Default to 1 if no pack size found
    return 1


def normalize_item_name(item_name):
    """
    Normalize item name for comparison (remove pack size info, extra spaces, etc.)
    """
    if not item_name:
        return ""
    
    # Remove pack size indicators for comparison
    normalized = item_name
    normalized = re.sub(r'\s*\d+\s*(ct|pk|count|pieces?|pack)\b', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Remove common suffixes that might vary
    normalized = re.sub(r'\s*Qty\s+\d+\s*\$?\s*$', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\s*Canceled\s+items?\s*\(\d+\)\s*$', '', normalized, flags=re.IGNORECASE)
    
    return normalized


def collate_sams_club_items(csv_path):
    """
    Collate identical items from Sam's Club receipts and calculate total quantities.
    
    Args:
        csv_path: Path to the Sam's Club receipts CSV
    
    Returns:
        DataFrame with aggregated items
    """
    # Read the CSV
    df = pd.read_csv(csv_path)
    
    print(f"Loaded {len(df)} items from {csv_path}")
    
    # Normalize item names for grouping
    df['normalized_item'] = df['item'].apply(normalize_item_name)
    df['pack_size'] = df['item'].apply(extract_pack_size)
    
    # Calculate actual quantity (unit_number * pack_size)
    df['actual_quantity'] = df['unit_number'] * df['pack_size']
    
    # Group by normalized item name
    aggregated = df.groupby('normalized_item').agg({
        'item': 'first',  # Keep the original item name (first occurrence)
        'actual_quantity': 'sum',  # Sum of all quantities
        'cost': 'sum',  # Sum of all costs
        'unit_number': 'sum',  # Total number of units purchased
        'pack_size': 'first'  # Pack size (should be same for same item)
    }).reset_index(drop=True)
    
    # Rename columns for clarity - only keep item, quantity, and cost
    aggregated = aggregated[['item', 'actual_quantity', 'cost']].copy()
    aggregated.columns = ['item', 'quantity', 'total_cost']
    
    # Sort by total cost descending
    aggregated = aggregated.sort_values('total_cost', ascending=False)
    
    return aggregated


def main():
    """
    Main function to collate Sam's Club items.
    """
    csv_path = Path('parsed_receipts/receipts_sams_club.csv')
    
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        return
    
    print("=" * 70)
    print("COLLATING SAM'S CLUB ITEMS")
    print("=" * 70)
    
    # Collate items
    aggregated_df = collate_sams_club_items(csv_path)
    
    # Save to CSV
    output_file = Path('parsed_receipts/receipts_sams_club_collated.csv')
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

