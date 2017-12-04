#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
import argparse
import boto3
import os
import threading
import time
import sys


class Spinner:
    spinning = False
    delay = 0.25

    @staticmethod
    def spinning_cursor():
        while 1:
            for cursor in '|/-\\':
                yield cursor

    def __init__(self, delay=None):
        self.spinner_generator = self.spinning_cursor()
        if delay and float(delay):
            self.delay = delay

    def spinner_task(self):
        while self.spinning:
            sys.stdout.write(next(self.spinner_generator))
            sys.stdout.flush()
            time.sleep(self.delay)
            sys.stdout.write('\b')
            sys.stdout.flush()

    def start(self):
        self.spinning = True
        threading.Thread(target=self.spinner_task).start()

    def stop(self):
        self.spinning = False
        time.sleep(self.delay)


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=args.region,
    )


def upload_cf_stack(template):
    print('Uploading stack')
    s3_resource = get_boto3_resource('s3')
    data = open(template, 'rb')
    s3_full_path = '{}/{}'.format(s3_base_path, os.path.basename(template))
    s3_resource.Bucket(s3_bucket).put_object(Key=s3_full_path, Body=data)
    return s3_full_path


def update_cf_stack(stack, s3_path):
    print('Updating CloudFormation stack')

    stack.update(
        TemplateURL='https://s3.amazonaws.com/{bucket}/{template}'.format(
            region=args.region,
            bucket=s3_bucket,
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

    spinner = Spinner()
    spinner.start()

    while True:
        stack.reload()
        status = stack.stack_status

        spinner.stop()
        sys.stdout.write("\033[K")  # Clear the line
        print("\rStack status: {} ".format(status), end="")

        if status in fail_statuses:
            print()  # Newline
            print(stack.stack_status_reason)
            raise Exception("Update failed!")
        elif status in success_statuses:
            print('                           ')  # Newline
            return
        else:
            spinner.start()
            time.sleep(15)
            continue


def main():
    s3_full_path = upload_cf_stack(args.template)
    print('Uploaded template to s3://{}/{}'.format(s3_bucket, s3_full_path))

    if not args.noupdate and args.stack:
        cf_resource = get_boto3_resource('cloudformation')
        stack = cf_resource.Stack(args.stack)
        update_cf_stack(stack, s3_full_path)
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
                        choices=['us-east-1', 'us-west-2'],
                        help='AWS Region')
    parser.add_argument('--project', '-p',
                        type=str,
                        choices=['preprocessing', 'infrastructure', 'statsapi', 'alerts'],
                        help='The project being deployed')
    parser.add_argument('--environment', '-e',
                        type=str,
                        choices=['infra', 'dev', 'qa', 'production'],
                        help='Environment')
    parser.add_argument('--no-update',
                        action='store_true',
                        dest='noupdate',
                        help='Skip updating CF stack')

    args = parser.parse_args()

    s3_bucket = 'biometrix-infrastructure-{}'.format(args.region)
    s3_base_path = 'cloudformation/{}-{}'.format(args.project, args.environment)
    main()
