#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
import argparse
import boto3
import os
import threading
import time
import sys

template_local_dir = os.path.abspath('../cloudformation')
template_s3_bucket = 'biometrix-infrastructure'
template_s3_path = 'cloudformation/'


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
