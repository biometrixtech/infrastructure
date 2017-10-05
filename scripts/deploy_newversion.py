#!/usr/bin/env python
# Upload a cloudformation template to S3, then run a stack update
import json

import boto3
import argparse
import os
import subprocess
import sys
import time
from subprocess import Popen, PIPE


def trigger_codebuild():
    git_revision = args.version if args.version != 'HEAD' else subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip()

    print('Triggering CodeBuild for version "{}"'.format(git_revision))
    codebuild_client = boto3.client('codebuild', region_name=args.region)
    res = codebuild_client.start_build(
        projectName='preprocessing-batchjob',
        sourceVersion=git_revision,
    )
    print('Build {}'.format(res['build']['id']))
    return res['build']['id']


def poll_for_codebuild_finish(codebuild_build_id):
    codebuild_client = boto3.client('codebuild', region_name=args.region)
    while True:
        build = codebuild_client.batch_get_builds(ids=[codebuild_build_id])['builds'][0]
        if build['buildStatus'] == 'IN_PROGRESS':
            print('CodeBuild job still running')
            time.sleep(30)
            continue
        elif build['buildStatus'] in ['FAILED', 'TIMED_OUT', 'FAULT', 'STOPPED']:
            raise Exception("CodeBuild build failed!")
        else:
            print('CodeBuild job complete')
            return
    pass


def update_cf_stack():
    print('Updating CloudFormation stack')
    cf_resource = boto3.resource('cloudformation', region_name=args.region)
    stack = cf_resource.Stack('preprocessing-{}'.format(args.environment))

    if args.job == 'all':
        jobs_to_update = ['BatchJobVersionDownloadandchunk', 'BatchJobVersionSessionprocess2', 'BatchJobVersionScoring', 'BatchJobVersionDatabaseupload']
    else:
        jobs_to_update = ['BatchJobVersion{}'.format(args.job)]

    batch_client = boto3.client('batch', region_name=args.region)
    batch_job_data = batch_client.describe_job_definitions(
        jobDefinitionName='preprocessing-batchjob'
    )['jobDefinitions']
    current_version = max([int(job['revision']) for job in batch_job_data])

    new_parameters = []
    for p in stack.parameters or {}:
        if p['ParameterKey'] in jobs_to_update:
            value = p['ParameterValue'].split(':')
            value[-1] = str(current_version + 1)
            print('Incrementing {} job version from {} to {}'.format(args.job, p['ParameterValue'], ':'.join(value)))
            new_parameters.append({'ParameterKey': p['ParameterKey'], 'ParameterValue': ':'.join(value)})
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
    run_process(cmd=["git", "branch", "-f", "{}-{}".format(args.environment, args.region), args.version])
    run_process(cmd=["git", "push", "origin", "{}-{}".format(args.environment, args.region)])


def run_process(cmd):
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    retcode = proc.wait()
    if retcode:
        sys.exit(retcode)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fire off a CodeBuild job, update the CloudFormation stack, and wait for CodeBuild completion')
    parser.add_argument('job',
                        type=str,
                        help='The job to update',
                        choices=['Downloadandchunk', 'Sessionprocess2', 'Scoring', 'Databaseupload', 'all'])
    parser.add_argument('version',
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

    build_id = trigger_codebuild()
    if not args.noupdate:
        update_cf_stack()
    poll_for_codebuild_finish(build_id)

