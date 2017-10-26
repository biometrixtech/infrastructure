#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
import json

import boto3
import argparse
import os
import sys
import time
from subprocess import check_output, CalledProcessError


def update_cf_stack():
    print('Updating CloudFormation stack')
    cf_resource = boto3.resource('cloudformation', region_name=args.region)
    stack = cf_resource.Stack('preprocessing-{}'.format(args.environment))

    new_parameters = []
    for p in stack.parameters or {}:
        if p['ParameterKey'] == 'BatchJobVersion':
            new_parameters.append({'ParameterKey': p['ParameterKey'], 'ParameterValue': args.batchjob_version})
        else:
            new_parameters.append({'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True})

    stack.update(
        TemplateURL='https://s3.amazonaws.com/biometrix-infrastructure-{region}/cloudformation/preprocessing-environment.yaml'.format(
            region=args.region,
        ),
        Parameters=new_parameters,
        Capabilities=['CAPABILITY_NAMED_IAM'],
    )


def update_git_branch():
    try:
        os.system("git -C /vagrant/PreProcessing branch -f {}-{} {}".format(args.environment, args.region, args.batchjob_version))
        os.system("git -C /vagrant/PreProcessing push origin {}-{}".format(args.environment, args.region))
    except CalledProcessError as e:
        print(e.output)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Deploy a new application version')
    parser.add_argument('batchjob_version',
                        type=str,
                        help='the Git version to deploy',
                        default='HEAD')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('--no-update',
                        action='store_true',
                        dest='noupdate',
                        help='Skip updating CF stack')

    args = parser.parse_args()

    update_git_branch()
    if not args.noupdate:
        update_cf_stack()

