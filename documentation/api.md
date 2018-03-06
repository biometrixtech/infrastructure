# API Infrastructure

## Overview

The APIs are constructed in a serverless structure using AWS's Route53, Amazon Certificate Manager, API Gateway and Lambda technologies, and various serverless data stores.

An API Gateway is set up with a basic proxy configuration which forwards all incoming requests to a single Lambda function backend. The Lambda function executes with a bespoke IAM Role. API Gateway's Custom Domains feature provisions a managed CloudFront distribution and Route53 records which expose the API at our custom endpoints [https://\<service\>.\<env\>.fathomai.com/v1](https://<service>.<env>.fathomai.com/v1) and [https://apis.\<env\>.fathomai.com/\<service\>](https://apis.\<env\>.fathomai.com/\<service\>). HTTPS security is provided by an Amazon Certificate Manager SSL Certificate, which must be created in the `us-east-1` region in order to be importable into CloudFront.

The backing Lambda function for each service is written in Python and uses the [Flask](http://flask.pocoo.org/) framework for routing and error handling, using the [flask-lambda](https://github.com/sivel/flask-lambda) integration to run the Flask application in a Lambda environment.

Data is stored in a number of different data stores, including DynamoDB (hardware/firmware, preprocessing/session), Cognito UserPool (hardware/accessory), and the legacy Postgres DB (hardware/sensor).

## Templating

The API is templated in the master `<service>-environment` CloudFormation template for each service.  The subservice comprises three resources: the Lambda function which will back the API, the custom IAM Role which the function will execute with, and a nested CloudFormation Stack which creates the API Gateway and associated resources according to a shared template.

The Hardware, Preprocessing, Alerts and User APIs all use Lambda functions which reference a zip archive location in the `biometrix-infrastructure-<region>` S3 bucket.  

## Deployment

Edits to application code should be made in the relevant codebase and committed to GitHub.  The infrastructure script:

```
deploy_lambda.py \
    --region <region> \
    --service <service> \
    --environment <env> \
    /path/to/lambda/code/folder
```

will zip the current working copy and deploy it to S3.  The resulting .zip file can also be used to update the lambda function directly.

Having deployed a new zip archive, the script:

```
deploy_cloudformation.py \
    --region <region> \
    --service <service> \
    --environment <env> \
    --subervice environment \
    <service>-<env>
```

Will update the CloudFormation stack and should deploy the new code to the lambda function.  If that update does not work (eg if CloudFormation thinks that the Lambda function does not need updating), you can update the function manually:

```
aws lambda update-function-code \
    --function-name <service>-<env>-apigateway-execute
    --zip-file fileb://path/to/lambda/code/zipfile
```

Alternatively, small edits can be made to the Lambda code directly in the AWS Console.  These edits __must__ be copied back into the git codebase and committed, or they _will_ be lost in future updates.
