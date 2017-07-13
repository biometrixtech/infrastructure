#!/usr/bin/env bash
ENV=dev
aws ssm put-parameter \
    --type SecureString \
    --name "preprocessing.$ENV.$1" \
    --value "$2" \
    --key-id "alias/preprocessing/$ENV" \
    --overwrite
