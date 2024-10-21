# Smart Load Balancer for Bedrock Endpoints

## Problem Statement

AWS Bedrock offers a robust platform for generative AI services, but **quota limitations in a single region** can hinder customers from fully leveraging these capabilities. Some organizations face the challenge of **exceeding their regional quota limits** for Bedrock endpoints. Even when multiple endpoints are available across different regions, users lack a mechanism to **intelligently distribute traffic** and utilize all available quotas efficiently. This results in:

- **Service interruptions** when quota limits are reached.
- **Underutilization of regional quotas**, as customers are manually routing traffic.
- Increased operational complexity for **cross-region API invocations**.

### Key Challenges:
1. **Per-minute quota**: Each Bedrock endpoint has a rate-limited quota, which resets every minute.
2. **Inefficient routing**: Without a smart distribution mechanism, traffic might be directed to already overloaded endpoints.
3. **Regional constraints**: Customers need a way to leverage multiple regions efficiently to avoid service degradation.

---

## Solution

The **Smart Load Balancer** provides an **automated solution** to these challenges. It uses an AWS Lambda function that dynamically routes requests across multiple Bedrock endpoints based on:

- **Available quota**: Traffic is routed to the endpoint with the **maximum quota** available at any given time.
- **Per-minute reset tracking**: The Lambda function **monitors and resets quotas** every minute, ensuring accurate tracking.
- **DynamoDB integration**: A DynamoDB table stores the **quota usage** and **last reset timestamp** for each endpoint.
- **API Gateway integration**: The Lambda function is exposed through API Gateway, allowing users to invoke the Bedrock service seamlessly.

### Workflow Overview:
1. **Quota Management**: Each time a request is processed, the Lambda function checks the **last reset timestamp**. If it detects a new minute, it **resets the used quota to zero**.
2. **Load Balancing Logic**: The function selects the **endpoint with the highest available quota** and routes the request accordingly.
3. **DynamoDB Update**: After invoking the selected Bedrock endpoint, the quota usage is updated in **DynamoDB**.
4. **API Gateway Invocation**: The entire process is accessible through **API Gateway**, making it easy to integrate with other systems or trigger requests programmatically.

---

## Why This Solution Works

- **Automated Quota Management**: No manual intervention is required to reset or monitor quotas.
- **Efficient Traffic Distribution**: Ensures that requests are routed to the most optimal endpoint, preventing failures due to quota exhaustion.
- **Cross-Region Utilization**: Unlocks the ability to **use multiple regions simultaneously**, maximizing the use of Bedrock services.
- **Cost-Effective**: Reduces the need for complex infrastructure or manual processes by leveraging **AWS services** like Lambda, DynamoDB, and API Gateway.

---

## AWS Services Used
- **AWS Lambda**: Runs the smart load balancer logic.
- **DynamoDB**: Tracks the quota usage, request count, and last reset timestamps for each endpoint.
- **API Gateway**: Exposes the Lambda function to external applications.
- **AWS Bedrock**: Provides the generative AI capabilities being accessed through this load balancer.

---

The following sections detail the **step-by-step process** for deploying the Lambda function, integrating it with API Gateway, and testing the entire setup.

## Step-by-Step Process

1. **Step 1: Create DynamoDB Table**

2. **Step 2: Deploy the Lambda Function**

4. **Step 3: Create API Gateway**

5. **Step 4: Get the Root Resource ID**

6. **Step 5: Create a New Resource under Root**

7. **Step 6: Set Up the POST Method**

8. **Step 7: Integrate Lambda with API Gateway**

9. **Step 8: Grant API Gateway Permission to Invoke Lambda**

10. **Step 9: Deploy the API**

11. **Step 10: Get the API URL**

12. **Step 11: Test the API**

---

### Step 1: Create DynamoDB Table

Create a **DynamoDB table** to store the **quota tracking information** for each endpoint. Below is the AWS CLI command to create the table:

```bash
aws dynamodb create-table \
  --table-name BedrockQuotaTracking \
  --attribute-definitions AttributeName=region,AttributeType=S \
  --key-schema AttributeName=region,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

**Explanation**:
- **Table Name**: `BedrockQuotaTracking`
- **Primary Key**: `region` (String) – This uniquely identifies each Bedrock endpoint by region.

Once the table is created, you’ll need to **add some initial data** to it. Below is a sample command to insert data for two regions:

```bash
aws dynamodb put-item \
  --table-name BedrockQuotaTracking \
  --item '{"region": {"S": "us-east-1"}, "used_quota": {"N": "0"}, "total_quota": {"N": "500"}, "request_count": {"N": "0"}, "last_reset": {"N": "0"}}'

aws dynamodb put-item \
  --table-name BedrockQuotaTracking \
  --item '{"region": {"S": "us-west-2"}, "used_quota": {"N": "0"}, "total_quota": {"N": "500"}, "request_count": {"N": "0"}, "last_reset": {"N": "0"}}'
```

These commands create two sample regions (`us-east-1` and `us-west-2`) with initial quotas.

---

### **Step 2: Deploy the Lambda Function**

1. **Create a Trust Policy for Lambda Execution**  
   Save the following content into a file named `trust-policy.json`. This policy allows **AWS Lambda** to assume the role.
    ```bash
    nano trust-policy.json
    ```

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Service": "lambda.amazonaws.com"
         },
         "Action": "sts:AssumeRole"
       }
     ]
   }
   ```

2. **Create the Lambda Execution Role using the Trust Policy**  
   Use the following command to create the role:

   ```bash
   aws iam create-role \
     --role-name LambdaExecutionRole \
     --assume-role-policy-document file://trust-policy.json
   ```

3. **Attach Policy to Access DynamoDB and Bedrock Models**  
   Create another file named `lambda-policy.json` with the following permissions:
    ```bash
    nano lambda-policy.json
    ```
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "dynamodb:GetItem",
           "dynamodb:PutItem",
           "dynamodb:UpdateItem",
           "dynamodb:Scan"
         ],
         "Resource": "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/BedrockQuotaTracking"
       },
       {
         "Effect": "Allow",
         "Action": [
           "bedrock:InvokeModel"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "logs:CreateLogGroup",
           "logs:CreateLogStream",
           "logs:PutLogEvents"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

   This policy allows:
   - **DynamoDB Access**: Full read/write access to the `BedrockQuotaTracking` table.
   - **Bedrock Access**: Permission to invoke any **Bedrock model**.
   - **CloudWatch Logs**: Access to create and write to **logs** for troubleshooting.

4. **Attach the Policy to the Role**  
   Use the following command to attach the policy to the role:

   ```bash
   aws iam put-role-policy \
     --role-name LambdaExecutionRole \
     --policy-name LambdaPolicy \
     --policy-document file://lambda-policy.json
   ```

5. **Verify the Role Creation**  
   Use the following command to confirm the role was created and the policy was attached successfully:

   ```bash
   aws iam get-role --role-name LambdaExecutionRole
   aws iam get-role-policy --role-name LambdaExecutionRole --policy-name LambdaPolicy
   ```

---

6. **Deploy the Lambda Function with the Execution Role**

    Ensure your **Lambda function** code is packaged into a ZIP file. 

    ```bash
    zip function.zip lambda_function.py
    ```

    Now that the **Lambda execution role** is created, you can use it while deploying the Lambda function. When you package and deploy the function, reference the **ARN** of the role you just created.

    ```bash
    aws lambda create-function \
    --function-name SmartLoadBalancer \
    --runtime python3.12 \
    --role arn:aws:iam::ACCOUNT_ID:role/LambdaExecutionRole \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://function.zip
    --timeout 300
    ```

    Note: Replace `ACCOUNT_ID` and `LambdaExecutionRole` with your IAM role and account ID.

---

### Step 3: Create API Gateway

Create a **REST API** using the following command:

```bash
aws apigateway create-rest-api \
  --name "BedrockSmartLoadBalancerAPI" \
  --description "API to route traffic to Bedrock endpoints based on quota" \
  --region us-east-1
```

This command will return a **REST API ID**. Store it for later steps.  
Sample response:
```json
{
    "id": "abcd1234",
    "name": "BedrockSmartLoadBalancerAPI",
    "createdDate": "2024-10-21T15:03:00Z"
}
```

---

### Step 4: Get the Root Resource ID

Use the API ID returned in the previous step to fetch the **root resource ID**.

```bash
aws apigateway get-resources --rest-api-id abcd1234
```

Response:
```json
{
    "items": [
        {
            "id": "a1b2c3",
            "path": "/"
        }
    ]
}
```

Note the **resource ID** (`a1b2c3` in this case).

---

### Step 5: Create a New Resource under Root

Create a new **resource** (path) called `/invoke`:

```bash
aws apigateway create-resource \
  --rest-api-id abcd1234 \
  --parent-id a1b2c3 \
  --path-part invoke
```

This command will return the new **resource ID** (e.g., `xyz123`).

---

### Step 6: Set Up the POST Method

Enable a **POST method** for the `/invoke` resource:

```bash
aws apigateway put-method \
  --rest-api-id abcd1234 \
  --resource-id xyz123 \
  --http-method POST \
  --authorization-type "NONE"
```

---

### Step 7: Integrate Lambda with API Gateway

Link the Lambda function to the API Gateway's POST method:

```bash
aws apigateway put-integration \
  --rest-api-id abcd1234 \
  --resource-id xyz123 \
  --http-method POST \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:ACCOUNT_ID:function:SmartLoadBalancer/invocations
```

Make sure to replace **ACCOUNT_ID** with your AWS account ID.

---

### Step 8: Grant API Gateway Permission to Invoke Lambda

Use the following command to allow API Gateway to invoke your Lambda function:

```bash
aws lambda add-permission \
  --function-name SmartLoadBalancer \
  --statement-id apigateway-invoke-permission \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn arn:aws:execute-api:us-east-1:ACCOUNT_ID:abcd1234/*/POST/invoke
```

---

### Step 9: Deploy the API

Create a **deployment** for the API in the `prod` stage:

```bash
aws apigateway create-deployment \
  --rest-api-id abcd1234 \
  --stage-name prod
```

---

### Step 10: Get the API URL

The deployed API will be accessible at the following endpoint:

```
https://{api-id}.execute-api.us-east-1.amazonaws.com/prod/invoke
```

Replace `{api-id}` with your actual **API ID** (e.g., `abcd1234`).

---

### Step 11: Test the API

Use `curl` to test the API with a sample request:

```bash
curl -X POST https://abcd1234.execute-api.us-east-1.amazonaws.com/dev/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Generate a song about the River Ganga"
  }'

```

Or you can use test_loadbalancer.py to test the implementation.
```bash
python3 test_loadbalancer.py
```
---

## Conclusion

With these steps, you have successfully:
- Created an API Gateway and linked it to your Lambda function.
- Deployed the API and tested it using `curl`.