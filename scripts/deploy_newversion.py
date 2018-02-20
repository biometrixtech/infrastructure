#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
from botocore.exceptions import ClientError
from subprocess import check_output, CalledProcessError
from colorama import Fore, Back, Style
from datetime import datetime
import __builtin__
import argparse
import boto3
import os
import sys
import threading
import time


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
        TemplateURL='https://s3.amazonaws.com/biometrix-infrastructure-{region}/cloudformation/preprocessing-{environment}/preprocessing-environment.yaml'.format(
            region=args.region,
            environment=args.environment,
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
    cutoff = datetime.now()

    spinner = Spinner()
    spinner.start()

    while True:
        stack.reload()
        status = stack.stack_status

        spinner.stop()
        sys.stdout.write("\033[K")  # Clear the line

        if status in fail_statuses:
            print("\rStack status: {}                        ".format(status), colour=Fore.RED)
            failure_resource_statuses = [
                'UPDATE_ROLLBACK_IN_PROGRESS',
                'CREATE_FAILED',
                'UPDATE_FAILED',
                'DELETE_FAILED'
            ]
            failure_events = [e for e in stack.events.all()
                              if e.timestamp.replace(tzinfo=None) > cutoff
                              and e.resource_status in failure_resource_statuses
                              and e.resource_status_reason is not None]
            print('\n'.join([e.resource_status_reason for e in failure_events]), colour=Fore.RED)
            return 1
        elif status in success_statuses:
            print("\rStack status: {}                        ".format(status), colour=Fore.GREEN)
            return 0
        else:
            print("\rStack status: {} ".format(status), colour=Fore.CYAN, end="")
            spinner.start()
            time.sleep(5)
            continue


def update_git_branch():
    try:
        git_dir = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../PreProcessing'))
        os.system("git -C {} branch -f {}-{} {}".format(git_dir, args.environment, args.region, args.batchjob_version))
        os.system("git -C {} push origin {}-{} --force".format(git_dir, args.environment, args.region))
    except CalledProcessError as e:
        print(e.output, colour=Fore.RED)
        raise


def print(*args, **kwargs):
    if 'colour' in kwargs:
        __builtin__.print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        __builtin__.print(*args, **kwargs)

        __builtin__.print(Style.RESET_ALL, end=end)

    else:
        __builtin__.print(*args, **kwargs)


def main():
    cf_resource = boto3.resource('cloudformation', region_name=args.region)
    stack = cf_resource.Stack('preprocessing-{}'.format(args.environment))

    update_git_branch()
    if not args.noupdate:
        try:
            update_cf_stack(stack)
        except ClientError as e:
            print(e, colour=Fore.RED)
            exit(1)

        exit(await_stack_update(stack))


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
