#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
from botocore.exceptions import ClientError
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


def get_boto3_resource(resource):
    return boto3.resource(
        resource,
        region_name=args.region,
    )


def update_cf_stack(stack, s3_path):
    print('Updating stack {} using template {}'.format(stack.stack_name, s3_path))
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
    templates = map_templates(args.project, args.environment, args.service)
    s3_resource = get_boto3_resource('s3')
    for source, dest in templates:
        s3_resource.Bucket(s3_bucket).put_object(Key=dest, Body=open(source, 'rb'))
        print('Uploaded template from {} to {}'.format(source, dest), colour=Fore.GREEN)

    if not args.noupdate and args.stack:
        cf_resource = get_boto3_resource('cloudformation')
        stack = cf_resource.Stack(args.stack)

        try:
            update_cf_stack(stack, templates[-1][1])
        except ClientError as e:
            if 'No updates are to be performed' in str(e):
                print('No updates are to be performed', colour=Fore.YELLOW)
                exit(0)
            else:
                print(e, colour=Fore.RED)
                exit(1)

        exit(await_stack_update(stack))

def map_templates(project, environment, service):
    if service in ['vpc', 'apigateway']:
        # These services, in any project, are drawn from the infrastructure repo
        project = 'infrastructure'
        return [(
            '/vagrant/Infrastructure/cloudformation/{service}.yaml'.format(service=service),
            'cloudformation/infrastructure-{environment}/{service}.yaml'.format(environment=environment, service=service),
        )]
    else:
        base_paths = {
            'alerts': '/vagrant/Alerts/cloudformation',
            'infrastructure': '/vagrant/Infrastructure/cloudformation',
            'preprocessing': '/vagrant/PreProcessing/cloudformation',
            'statsapi': '/vagrant/StatsAPI/serverless',
            'users': '/vagrant/Users/cloudformation',
        }
        valid_services = {
            'alerts': ['pipeline'],
            'infrastructure': [],
            'preprocessing': ['compute', 'ingest', 'monitoring', 'pipeline'],
            'statsapi': [],
            'users': [],
        }
        if project in valid_services:
            if service in valid_services[project] or service == 'environment':
                templates = [(
                    '{basepath}/{project}-{service}.yaml'.format(basepath=base_paths[project], project=project, service=service),
                    'cloudformation/{project}-{environment}/{project}-{service}.yaml'.format(project=project, environment=environment, service=service)
                )]
                if service == 'environment' and project != 'infrastructure':
                    # For non-infrastructure projects, updating the environment means updating all the child stacks
                    templates += [t for s in valid_services[project] for t in map_templates(project, environment, s)]
                return templates
            else:
                print('Invalid service for project', colour=Fore.RED)
                exit(1)
        else:
                print('Invalid project', colour=Fore.RED)
                exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a template to S3, and maybe update a CF stack using it')
    # parser.add_argument('template',
    #                     type=str,
    #                     help='the name of a template file')
    parser.add_argument('stack',
                        type=str,
                        nargs='?',
                        default='',
                        help='the name of a CF stack to update')
    parser.add_argument('--region', '-r',
                        type=str,
                        choices=['us-east-1', 'us-west-2'],
                        help='AWS Region')
    parser.add_argument('--project', '-p',
                        type=str,
                        choices=['preprocessing', 'infrastructure', 'statsapi', 'alerts', 'users'],
                        help='The project being deployed')
    parser.add_argument('--environment', '-e',
                        type=str,
                        choices=['infra', 'dev', 'qa', 'production'],
                        help='Environment')
    parser.add_argument('--service', '-s',
                        type=str,
                        help='Service')
    parser.add_argument('--template-file',
                        type=str,
                        help='Override template file')
    parser.add_argument('--no-update',
                        action='store_true',
                        dest='noupdate',
                        help='Skip updating CF stack')

    args = parser.parse_args()

    s3_bucket = 'biometrix-infrastructure-{}'.format(args.region)
    s3_base_path = 'cloudformation/{}-{}'.format(args.project, args.environment)
    main()
