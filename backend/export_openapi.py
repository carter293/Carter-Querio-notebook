#!/usr/bin/env python3
"""Export OpenAPI specification to JSON file."""
import json
from main import app

if __name__ == '__main__':
    with open('openapi.json', 'w') as f:
        json.dump(app.openapi(), f, indent=2)
    print('OpenAPI spec exported to openapi.json')

