#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
from __future__ import print_function
from botocore.exceptions import ClientError
from colorama import Fore, Style
from datetime import datetime
from subprocess import CalledProcessError
import __builtin__
import argparse
import boto3
import os
import re
import sys
import threading
import time

subservice_stack_mapping = {
    'preprocessing': {
        'compute': 'ComputeCluster',
        'ingest': 'IngestStack',
        'monitoring': 'MonitoringCluster',
        'pipeline': 'PipelineCluster',
    }
}


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


def get_stack_name():
    cloudformation_client = boto3.client('cloudformation', region_name=args.region)
    res = cloudformation_client.get_paginator('list_stacks').paginate(PaginationConfig={'MaxItems': 99999})
    stacks = [s for page in res for s in page['StackSummaries']]

    if args.subservice == 'environment':
        stack_names = [s['StackName'] for s in stacks
                       if s['StackStatus'] != 'DELETE_COMPLETE'
                       and s['StackName'] == '{}-{}'.format(args.service, args.environment)]
    else:
        stack_prefix = '{}-{}-{}'.format(
            args.service,
            args.environment,
            subservice_stack_mapping[args.service][args.subservice]
        )
        stack_names = [s['StackName'] for s in stacks
                       if s['StackStatus'] != 'DELETE_COMPLETE'
                       and s['StackName'].startswith(stack_prefix)]

    if len(stack_names):
        return stack_names[0]
    else:
        print('Could not find stack to update', colour=Fore.RED)
        exit(1)


def update_cf_stack(stack, s3_path):
    print('Updating stack {} using template s3://{}/{}'.format(stack.stack_name, s3_bucket_name, s3_path))
    drop_params = args.drop_params.split(',')
    stack.update(
        TemplateURL='https://s3.amazonaws.com/{bucket}/{template}'.format(
            region=args.region,
            bucket=s3_bucket_name,
            template=s3_path,
        ),
        Parameters=[{'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True}
                    for p in stack.parameters or {}
                    if p['ParameterKey'] not in drop_params],
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


def update_git_branch(branch_name):
    try:
        git_dir = get_git_dir()
        os.system("git -C {} update-ref refs/heads/{} {}".format(git_dir, branch_name, args.version))
        os.system("git -C {} push origin {} --force".format(git_dir, branch_name))
    except CalledProcessError as e:
        print(e.output, colour=Fore.RED)
        raise


def get_git_dir():
        git_repo_name = {
            'alerts': 'Alerts',
            'hardware': 'Hardware',
            'infrastructure': 'Infrastructure',
            'preprocessing': 'PreProcessing',
            'statsapi': 'StatsAPI',
            'users': 'Users',
        }[args.service]
        return os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../{}'.format(git_repo_name)))


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
    templates = map_templates(args.service, args.environment, args.subservice, args.version)

    s3_bucket = boto3.resource('s3').Bucket(s3_bucket_name)
    if args.version == '0' * 40:
        if args.environment != 'dev':
            print('Working copy can only be deployed to dev', colour=Fore.RED)
            exit(1)

        for source, dest in templates:
            s3_bucket.put_object(Key=dest, Body=open(source, 'rb'))
            print('Uploaded template from {} to s3://{}/{}'.format(source, s3_bucket.name, dest), colour=Fore.GREEN)

    else:
        # Check that the CF templates have actually been uploaded
        s3_bucket.Object(templates[0][1]).wait_until_exists()
        print('Template exists')

    if not args.noupdate:
        stack = boto3.resource('cloudformation', region_name=args.region).Stack(get_stack_name())

        try:
            update_cf_stack(stack, templates[0][1])
        except ClientError as e:
            if 'No updates are to be performed' in str(e):
                print('No updates are to be performed', colour=Fore.YELLOW)
            else:
                print(e, colour=Fore.RED)
                exit(1)

        res = await_stack_update(stack)
        if res == 0 and args.subservice == 'environment':
            # Update git reference
            # TODO
            print('Updating git reference')
            update_git_branch('{}-{}'.format(args.environment, args.region))
            if args.service == 'preprocessing':
                # We also implicitly deployed a new version of the application here
                update_git_branch('{}-{}-app'.format(args.environment, args.region))
            pass

        exit(res)


def map_templates(service, environment, subservice, version):
    if subservice in ['vpc', 'apigateway']:
        # These subservices, in any service, are drawn from the infrastructure repo
        return [(
            '/vagrant/Infrastructure/cloudformation/{subservice}.yaml'.format(subservice=subservice),
            'cloudformation/infrastructure-{environment}/{subservice}.yaml'.format(environment=environment, subservice=subservice),
        )]
    else:
        base_paths = {
            'alerts': '/vagrant/Alerts/cloudformation',
            'infrastructure': '/vagrant/Infrastructure/cloudformation',
            'hardware': '/vagrant/Hardware/cloudformation',
            'preprocessing': '/vagrant/PreProcessing/cloudformation',
            'statsapi': '/vagrant/StatsAPI/cloudformation',
            'users': '/vagrant/Users/cloudformation',
        }
        valid_subservices = {
            'alerts': ['pipeline'],
            'infrastructure': ['timeserver', 'gitsync', 'lambci'],
            'hardware': [],
            'preprocessing': ['compute', 'ingest', 'monitoring', 'pipeline'],
            'statsapi': [],
            'users': [],
        }
        if service in valid_subservices:
            if subservice in valid_subservices[service] or subservice == 'environment':
                templates = [(
                    '{basepath}/{service}-{subservice}.yaml'.format(
                        basepath=base_paths[service],
                        service=service,
                        subservice=subservice
                    ),
                    'cloudformation/{service}/{version}/{service}-{subservice}.yaml'.format(
                        service=service,
                        version=version,
                        subservice=subservice
                    )
                )]
                if subservice == 'environment' and service != 'infrastructure':
                    # For non-infrastructure services, updating the environment means updating all the child stacks
                    templates += [t for s in valid_subservices[service] for t in map_templates(service, environment, s, version)]
                return templates
            else:
                print('Invalid subservice for service', colour=Fore.RED)
                exit(1)
        else:
                print('Invalid service', colour=Fore.RED)
                exit(1)


if __name__ == '__main__':
    def git_commit(x):
        if not re.match('^[0-9a-f]{40}$', x):
            raise argparse.ArgumentTypeError('Version number must be a 40-hex-digit git hash')
        return x

    parser = argparse.ArgumentParser(description='Upload a template to S3, and maybe update a CF stack using it')
    parser.add_argument('--region',
                        type=str,
                        choices=['us-east-1', 'us-west-2'],
                        default='us-west-2',
                        help='AWS Region')
    parser.add_argument('service',
                        type=str,
                        choices=[
                            'alerts',
                            'infrastructure',
                            'hardware',
                            'preprocessing',
                            'statsapi',
                            'users',
                        ],
                        help='The service being deployed')
    parser.add_argument('environment',
                        type=str,
                        choices=['infra', 'dev', 'qa', 'production'],
                        help='Environment')
    parser.add_argument('subservice',
                        type=str,
                        help='Service')
    parser.add_argument('version',
                        type=git_commit,
                        help='the version to deploy')
    parser.add_argument('--no-update',
                        action='store_true',
                        dest='noupdate',
                        help='Skip updating CF stack')
    parser.add_argument('--drop-params',
                        dest='drop_params',
                        default='',
                        help='Parameters to drop from the template, comma-delimited')

    args = parser.parse_args()

    s3_bucket_name = 'biometrix-infrastructure-{}'.format(args.region)
    main()
