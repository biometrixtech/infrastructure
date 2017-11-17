#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update

import argparse
import boto3
import os
import time

template_local_dir = os.path.abspath('../cloudformation')
template_s3_bucket = 'biometrix-infrastructure'
template_s3_path = 'cloudformation/'


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=args.region,
    )


def upload_cf_stack(template):
    print('Uploading stack')
    s3_resource = get_boto3_resource('s3')
    data = open(template, 'rb')
    s3_path = template_s3_path + os.path.basename(template)
    s3_resource.Bucket(template_s3_bucket + '-' + args.region).put_object(Key=s3_path, Body=data)
    return s3_path


def update_cf_stack(stack, s3_path):
    print('Updating CloudFormation stack')

    stack.update(
        TemplateURL='https://s3.amazonaws.com/{bucket}/{template}'.format(
            region=args.region,
            bucket=template_s3_bucket + '-' + args.region,
            template=s3_path,
        ),
        Parameters=[{'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True} for p in stack.parameters or {}],
        Capabilities=['CAPABILITY_NAMED_IAM'],
    )


def await_stack_update(stack):
    fail_statuses = [
        'UPDATE_ROLLBACK_IN_PROGRESS',
        'UPDATE_ROLLBACK_FAILED',
        'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
        'UPDATE_ROLLBACK_COMPLETE'
    ]
    success_statuses = ['UPDATE_COMPLETE', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS']

    while True:
        stack.reload()
        status = stack.stack_status
        print("Stack status: {}".format(status))
        if status in fail_statuses:
            print(stack.stack_status_reason)
            raise Exception("Update failed!")
        elif status in success_statuses:
            print('Update complete')
            return
        else:
            print('Update still running')
            time.sleep(5)
            continue
    pass


def main():
    s3_path = upload_cf_stack(args.template)

    if args.stack != '':
        cf_resource = get_boto3_resource('cloudformation')
        stack = cf_resource.Stack(args.stack)
        update_cf_stack(stack, s3_path)
        await_stack_update(stack)


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
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')

    args = parser.parse_args()
    main()
