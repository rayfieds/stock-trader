import yaml
import json

# Read YAML
with open('portfolio.yaml', 'r') as f:
    data = yaml.safe_load(f)

# Convert to JSON (compact, single line)
json_string = json.dumps(data)

# Print for copying to GitHub
print("Copy this to GitHub Secret PORTFOLIO_DATA:")
print(json_string)

# Or save to file
with open('portfolio.json', 'w') as f:
    json.dump(data, f, indent=2)