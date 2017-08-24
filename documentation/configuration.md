# Configuration

Batch jobs are configured via parameters stored in Amazon Simple Systems Manager's Parameter Store service.  This has built-in IAM authentication and KMS integration.

## Setting configuration

To set a configuration variable, run:

```shell
function setconfig {
    ENV=dev
    aws ssm put-parameter \
        --type SecureString \
        --name "preprocessing.$ENV.$1" \
        --value "$2" \
        --key-id "alias/preprocessing/$ENV" \
        --overwrite
}
setconfig db_host "dev.c8ulvgkxnnos.us-west-2.rds.amazonaws.com"
```
Configuration changes will be applied immediately to all newly-started jobs (ie not to jobs that have already begun running, but yes to jobs that are scheduled but have not yet started running).

To check the value of a configurtation variable, run:
```shell
function getconfig {
    ENV=dev
    aws ssm get-parameters \
        --names "preprocessing.$ENV.$1" \
        --with-decryption \
    | jq -r .Parameters[0].Value
}
getconfig db_host
```
(note this requires `jq` to be installed).

## Permissions

TODO

## Installing a new model file

```shell
REGION=us-west-2
cat <<EOF > install-globalmodels.json
{
    "jobDefinitionName": "install-globalmodels",
    "type": "container",
    "containerProperties": {
        "image": "faisyl/alpine-nfs",
        "vcpus": 1,
        "memory": 128,
        "jobRoleArn": "arn:aws:iam::887689817172:role/preprocessing-batchjob-$REGION",
        "command": [
            "/bin/sh", "-c", 
            " \
                mkdir /net /net/efs ; \
                mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=10,retrans=2 efs.internal:/ /net/efs 2>&1 ; \
                apk -v --update add python py-pip && pip install awscli ; \
                aws s3 cp s3://biometrix-globalmodels/dev/grf_model_v2_0.h5 /net/efs/globalmodels/grf_model_v2_0.h5 ; \
                aws s3 cp s3://biometrix-globalmodels/dev/scaler_model_v2_0.pkl /net/efs/globalscalers/scaler_model_v2_0.pkl ; \
            "
        ],
        "readonlyRootFilesystem": false,
        "privileged": true
    }
}
EOF
aws batch register-job-definition --region $REGION --cli-input-json file://install-globalmodels.json
aws batch submit-job \
    --region $REGION \
    --job-name install-globalmodels \
    --job-queue preprocessing-dev-compute \
    --job-definition arn:aws:batch:$REGION:887689817172:job-definition/install-globalmodels:4
```
