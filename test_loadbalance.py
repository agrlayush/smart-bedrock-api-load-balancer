import requests
import json

url = "https://{api-gateway-id}.execute-api.us-east-1.amazonaws.com/prod/invoke"

payload = json.dumps({
  "prompt": "What is the capita of India? Answer only the name of the city. Skip the preamble."
})
headers = {
  'Content-Type': 'application/json'
}

num_requests = 3

for _ in range(num_requests):
    response = requests.request("POST", url, headers=headers, data=payload)
    print(response.text)