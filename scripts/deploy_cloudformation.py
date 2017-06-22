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
    )


def upload_cf_stack(template):
    print('Uploading stack')
    s3_resource = get_boto3_resource('s3')
    data = open(template, 'rb')
    s3_path = template_s3_path + os.path.basename(template)
    s3_resource.Bucket(template_s3_bucket + '-' + aws_region).put_object(Key=s3_path, Body=data)
    return s3_path


def update_cf_stack(stack_name, uploaded_path):
    print('Updating CloudFormation stack')
    cf_resource = get_boto3_resource('cloudformation')
    stack = cf_resource.Stack(stack_name)

    stack.update(
        TemplateURL='https://s3.amazonaws.com/{bucket}/{template}'.format(
            region=aws_region,
            bucket=template_s3_bucket + '-' + aws_region,
            template=uploaded_path,
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

    uploaded_path = upload_cf_stack(args.template)

    if args.stack != '':
        update_cf_stack(args.stack, uploaded_path)

