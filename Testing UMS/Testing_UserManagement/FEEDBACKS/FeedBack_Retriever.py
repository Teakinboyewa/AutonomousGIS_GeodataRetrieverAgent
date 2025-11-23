# Get Feedbacks GIS Copilot

import requests
import json

# Configuration
developer_api_key = "gibd-services-4BmoEZWbZZgBvUuz52LXnbDM" #tea5209@psu.edu
url = f"https://www.gibd.online/api/download_feedback"

data = {"service":"GIS Copilot",
        "dev_api_key": developer_api_key}

# Send POST request
response = requests.post(
    url,
    headers={"Content-Type": "application/json"},
    json=data
)

# Handle response
if response.status_code == 200:
    result = response.json()
    print("Data retrieved successfully!")
    print(f"Total records: {result['count']}")
    print(json.dumps(result, indent=2))
else:
    print(f"Error {response.status_code}: {response.text}")