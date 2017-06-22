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

