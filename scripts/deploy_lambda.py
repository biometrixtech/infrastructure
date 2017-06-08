#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update

import boto3
import argparse
import os

aws_region = 'us-east-1'
template_local_dir = os.path.abspath('../cloudformation')
template_s3_bucket = 'biometrix-preprocessing-infrastructure'
template_s3_path = 'cloudformation/'


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=aws_region,
        # aws_access_key_id=session_token.access_key_id,
        # aws_secret_access_key=session_token.secret_access_key,
        # aws_session_token=session_token.session_token
    )


def upload_cf_stack(template):
    print('Uploading stack')
    s3_resource = get_boto3_resource('s3')
    data = open(template, 'rb')
    s3_resource.Bucket(template_s3_bucket).put_object(Key=template_s3_path + template, Body=data)


def update_cf_stack(stack_name, template):
    print('Updating CloudFormation stack')
    cf_resource = get_boto3_resource('cloudformation')
    stack = cf_resource.Stack(stack_name)

    stack.update(
        TemplateURL='https://s3.amazonaws.com/{bucket}/{path}{template}'.format(
            region=aws_region,
            bucket=template_s3_bucket,
            path=template_s3_path,
            template=template
        ),
        Parameters=[{'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True} for p in stack.parameters or {}],
        Capabilities=['CAPABILITY_NAMED_IAM'],
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a template to S3, and maybe update a CF stack using it')
    parser.add_argument('template',
                        type=str,
                        help='the name of a template file')
    parser.add_argument('stack',
                        type=str,
                        nargs='?',
                        default='',
                        help='the name of a CF stack')
    # parser.add_argument('--mfatoken', '-t',
    #                     type=str,
    #                     default='',
    #                     help='MFA token value')

    args = parser.parse_args()

    upload_cf_stack(args.template)

    if args.stack != '':
        update_cf_stack(args.stack, args.template)

