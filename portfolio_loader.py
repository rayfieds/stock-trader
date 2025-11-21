"""
Portfolio Loader - Handles both simple and tracking formats
"""

import os
import json
import yaml


def load_portfolio_from_secret():
    """Load portfolio from GitHub secret or local file
    
    Supports flexible format:
      VFV.TO:
        shares: 30
        avg_buy_price: 163.33    # Optional
    
    Or simple:
      VFV.TO: 30                 # Just shares
    """
    
    # Try to load from environment variable (GitHub Secret)
    portfolio_json = os.environ.get('PORTFOLIO_DATA')
    
    if portfolio_json:
        config = json.loads(portfolio_json)
    else:
        # Running locally
        try:
            with open('portfolio.yaml', 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                "portfolio.yaml not found! Create it or set PORTFOLIO_DATA secret."
            )
    
    # Normalize portfolio format
    config['portfolio'] = normalize_portfolio_format(config.get('portfolio', {}))
    
    return config


def normalize_portfolio_format(portfolio):
    """Convert any format to standard tracking format
    
    Input examples:
      VFV.TO: 30                                    # Simple
      VFV.TO: {shares: 30}                          # Dict without price
      VFV.TO: {shares: 30, avg_buy_price: 163.33}  # Full tracking
    
    Output is always:
      VFV.TO: {shares: 30, avg_buy_price: 163.33 or None}
    """
    
    normalized = {}
    
    for ticker, data in portfolio.items():
        if isinstance(data, (int, float)):
            # Simple format: VFV.TO: 30
            normalized[ticker] = {
                'shares': data,
                'avg_buy_price': None
            }
        elif isinstance(data, dict):
            # Dict format
            normalized[ticker] = {
                'shares': data.get('shares', 0),
                'avg_buy_price': data.get('avg_buy_price')
            }
        else:
            print(f"⚠️  Unknown format for {ticker}: {data}")
            continue
    
    return normalized


def calculate_gain(portfolio, ticker, current_price):
    """Calculate gain/loss for a position
    
    Returns dict with gain info, or None if no buy price
    """
    holding = portfolio.get(ticker, {})
    
    if not isinstance(holding, dict):
        return None
    
    shares = holding.get('shares', 0)
    avg_buy_price = holding.get('avg_buy_price')
    
    if not avg_buy_price or shares == 0:
        return None
    
    # Calculate gains
    cost_basis = shares * avg_buy_price
    current_value = shares * current_price
    gain_amount = current_value - cost_basis
    gain_pct = (gain_amount / cost_basis) * 100
    
    return {
        'cost_basis': cost_basis,
        'current_value': current_value,
        'gain_amount': gain_amount,
        'gain_pct': gain_pct,
        'avg_buy_price': avg_buy_price
    }


# Example usage
if __name__ == "__main__":
    config = load_portfolio_from_secret()
    
    print("Portfolio loaded:")
    for ticker, holding in config['portfolio'].items():
        shares = holding['shares']
        buy_price = holding['avg_buy_price']
        
        if buy_price:
            print(f"  {ticker}: {shares} shares @ ${buy_price:.2f} (tracking gains)")
        else:
            print(f"  {ticker}: {shares} shares (no buy price)")
    
    print(f"\nCash: ${config['cash']:,.2f}")