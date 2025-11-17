import os
import json
import yaml

def load_portfolio_from_secret():
    
    # Try to load from environment variable (GitHub Secret)
    portfolio_json = os.environ.get('PORTFOLIO_DATA')
    
    if portfolio_json:
        # Running on GitHub Actions - use secret
        return json.loads(portfolio_json)
    else:
        # Running locally - use portfolio.yaml
        with open('portfolio.yaml', 'r') as f:
            return yaml.safe_load(f)

# Usage in your agent
config = load_portfolio_from_secret()