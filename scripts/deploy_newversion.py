#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
import boto3
import argparse
import os
import sys
import threading
import time
from subprocess import check_output, CalledProcessError


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


def update_cf_stack(stack):
    print('Updating CloudFormation stack')

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


def update_git_branch():
    try:
        os.system("git -C /vagrant/PreProcessing branch -f {}-{} {}".format(args.environment, args.region, args.batchjob_version))
        os.system("git -C /vagrant/PreProcessing push origin {}-{}".format(args.environment, args.region))
    except CalledProcessError as e:
        print(e.output)
        raise


def main():
    cf_resource = boto3.resource('cloudformation', region_name=args.region)
    stack = cf_resource.Stack('preprocessing-{}'.format(args.environment))

    update_git_branch()
    if not args.noupdate:
        update_cf_stack(stack)
        await_stack_update(stack)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Deploy a new application version')
    parser.add_argument('batchjob_version',
                        type=str,
                        help='the Git version to deploy',
                        default='HEAD')
    parser.add_argument('--region', '-r',
                        type=str,
                        choices=['us-east-1', 'us-west-2'],
                        help='AWS Region')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        choices=['infra', 'dev', 'qa', 'production'],
                        default='dev')
    parser.add_argument('--no-update',
                        action='store_true',
                        dest='noupdate',
                        help='Skip updating CF stack')

    args = parser.parse_args()

    main()

