# Installation

## Setting up Atlas peering

1. Create the service with `MongodbPeeringId` and `MongodbPeeringCidr` set to the empty string.  Make sure that you choose a value for `VpcCidr` which does not conflict with any existing peering connections to the Atlas cluster.

2. Update the stack to set `MongodbPeeringCidr` to the correct CIDR range for the Atlas cluster.  This will prompt the service to be placed into a VPC ready for peering.

3. Take the id of the VPC

NOTE: this is all out-of-date as of March 2018.

## Setting up a new environment / region

### Infrastructure

If this is a new region, create a new CloudFormation stack `preprocessing-infrastructure` using the `infrastructure.template` template:
 
```shell
TODO
```

This creates the S3 bucket `biometrix-preprocessing-infrastructure-<REGION>`.  Now upload the SFN-Batch custom integration lambda and create a new CF stack `preprocessing-aws-sfn-batch` 

```shell
./deploy_lambda.py \
    --region us-west-2 \
    --project preprocessing \
    --environment <env>
    /vagrant/aws-sfn-batch/lambdas/sfn_batch.py

./deploy_cloudformation.py \
    --region us-west-2 /vagrant/aws-sfn-batch/cloudformation/sfn-batch.template

aws cloudformation create-stack \
    --region us-west-2 \
    --stack-name preprocessing-aws-sfn-batch \
    --template-url https://s3.amazonaws.com/biometrix-infrastructure-<REGION>/cloudformation/sfn-batch.template \
    --parameters '[{"ParameterKey":"S3Bucket","ParameterValue":"biometrix-preprocessing-infrastructure-<REGION>"},{"ParameterKey":"Project","ParameterValue":"preprocessing"}]' \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags '[{"Key":"Project","Value":"preprocessing"},{"Key":"Environment","Value":"infra"}]'
```

This creates the Lambda functions `preprocessing-sfn-batch-schedule` and `preprocessing-sfn-batch-respond`.

```shell
./deploy_lambda.py --region us-west-2 /vagrant/aws-cloudformation-polyfill/lambdas/aws_cloudformation_polyfill.py

./deploy_cloudformation.py --region us-west-2 /vagrant/aws-cloudformation-polyfill/cloudformation/aws-cloudformation-polyfill.template

aws cloudformation create-stack \
    --region us-west-2 \
    --stack-name preprocessing-aws-cloudformation-polyfill \
    --template-url https://s3.amazonaws.com/biometrix-preprocessing-infrastructure-us-west-2/cloudformation/aws-cloudformation-polyfill.template \
    --parameters '[{"ParameterKey":"S3Bucket","ParameterValue":"biometrix-preprocessing-infrastructure-us-west-2"}]' \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags '[{"Key":"Project","Value":"preprocessing"},{"Key":"Environment","Value":"infra"}]'
```

This creates the Lambda functions TODO.

Finally create the security stack, which creates region-wide IAM service roles

```shell
./deploy_cloudformation.py --region us-west-2 /vagrant/Infrastructure/cloudformation/security.template

aws cloudformation create-stack \
    --region us-west-2 \
    --stack-name preprocessing-security \
    --template-url https://s3.amazonaws.com/biometrix-preprocessing-infrastructure-us-west-2/cloudformation/security.template \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags '[{"Key":"Project","Value":"preprocessing"},{"Key":"Environment","Value":"infra"}]'
```

### Environment

To set up a new environment, create a CloudFormation stack `preprocessing-<ENVIRONMENT>` in the region you want to deploy to.

```shell
./deploy_cloudformation.py --region us-west-2 /vagrant/Infrastructure/cloudformation/compute.template
./deploy_cloudformation.py --region us-west-2 /vagrant/Infrastructure/cloudformation/pipeline.template
./deploy_cloudformation.py --region us-west-2 /vagrant/Infrastructure/cloudformation/environment.template

aws cloudformation create-stack \
    --region us-west-2 \
    --stack-name preprocessing-<ENVIRONMENT> \
    --template-url https://s3.amazonaws.com/biometrix-preprocessing-infrastructure-us-west-2/cloudformation/aws-cloudformation-polyfill.template \
    --parameters '[{"ParameterKey":"S3Bucket","ParameterValue":"biometrix-preprocessing-infrastructure-us-west-2"}]' \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags '[{"Key":"Project","Value":"preprocessing"},{"Key":"Environment","Value":"infra"}]'
```

The Elastic File System in the environment needs to be initialised with a directory structure.  This can be
achieved by registering a Batch Job and then running it on the compute cluster:

```shell
/vagrant/Infrastructure/scripts/initialise_efs.py --region us-west-2 --environment dev
```

Setting the `MongoDbPeeringVpc` parameters in the template will set up the peering connection and create the necessary routes in the _environment's_ VPC, but you need to create the corresponding routes in the peered VPC manually.
