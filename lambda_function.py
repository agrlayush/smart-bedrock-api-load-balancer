import boto3
import time
import json
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# DynamoDB table name (from environment variable or hardcoded)
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "BedrockQuotaTracking")

# Initialize clients
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)

def get_available_endpoints():
    """Fetch all endpoints and their quotas from DynamoDB."""
    response = table.scan()
    return response.get('Items', [])

# This is a costly operation. Should be moved to a event bridge based implementation for production.
def reset_if_needed(endpoint): 
    """Reset the quota if the last reset was in a previous minute."""
    current_time = int(time.time())  # Current timestamp in seconds
    last_reset = endpoint.get('last_reset', 0)

    # Check if we are in a new minute
    if current_time // 60 > last_reset // 60:
        # Reset the used quota and update the timestamp
        table.update_item(
            Key={'region': endpoint['region']},
            UpdateExpression="SET used_quota = :zero, last_reset = :now",
            ExpressionAttributeValues={':zero': 0, ':now': current_time}
        )
        endpoint['used_quota'] = 0  # Ensure the in-memory object reflects the reset

def select_best_endpoint(endpoints):
    """Select the endpoint with the highest available quota.
    This will continue to return a region even if quota is depleted to 0.
    Make changes here if you want to handle quota depletion.
    """
    return max(endpoints, key=lambda x: x['total_quota'] - x['used_quota'])

def update_quota(region, increment=1):
    """Update the used quota and request count for a region."""
    table.update_item(
        Key={'region': region},
        UpdateExpression="SET used_quota = used_quota + :inc, request_count = request_count + :one",
        ExpressionAttributeValues={':inc': increment, ':one': 1}
    )

def lambda_handler(event, context):
    # Get the prompt from the body
    print(event)
    try:
        body = json.loads(event["body"])
        prompt = body.get("prompt")
        if not prompt:
            # prompt = "what is capital of india?"
            return {"statusCode": 400, "body": "Prompt is required"}
    except (ValueError, KeyError):
        return {"statusCode": 400, "body": "Invalid input"}
    
    try:
        # Get available endpoints and their quota status
        endpoints = get_available_endpoints()
        if not endpoints:
            return {"statusCode": 500, "body": "No endpoints available"}

        # Reset quotas if needed for each endpoint
        # This is a costly operation. Should be moved to a event bridge based implementation for production.
        for endpoint in endpoints:
            reset_if_needed(endpoint)

        # Select the endpoint with the highest available quota
        selected_endpoint = select_best_endpoint(endpoints)
        region = selected_endpoint['region']

        # Initialize the Bedrock runtime client for the selected region
        try:
            bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        except Exception as e:
            return {"statusCode": 500, "body": f"Error initializing Bedrock client: {str(e)}"}
            
            
        formatted_prompt = f"""
            Human: {prompt}
            Assistant:
        """
        
        # Call Bedrock endpoint (example payload    
        messages_payload = {
            "anthropic_version": "bedrock-2023-05-31",    
            "max_tokens": 3000,
            "messages": [
                {"content": f"Human: {formatted_prompt}", "role": "user"}
            ]
        }
        # Sending the request to the selected endpoint
        try:
            bedrock_response = bedrock_client.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                contentType='application/json',
                accept='application/json',
                body=json.dumps(messages_payload)
            )
            result = json.loads(bedrock_response['body'].read().decode())
        except Exception as e:
            return {"statusCode": 500, "body": f"Bedrock invocation failed: {str(e)}"}

        # Update quota usage for the selected endpoint
        update_quota(region)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "region": region,
                "response": result
            })
        }
    except ClientError as e:
        return {"statusCode": 500, "body": str(e)}
