#!/usr/bin/env python
# Initialise a new EFS filesystem
import json

import boto3
import argparse
import time


def register_job_definition():
    res = batch_client.register_job_definition(
        jobDefinitionName="initialise-efs",
        type="container",
        containerProperties={
            "image": "faisyl/alpine-nfs",
            "vcpus": 1,
            "memory": 128,
            "command": [
                "/bin/sh", "-c",
                " \
                    mkdir /net /net/efs ; \
                    mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=10,retrans=2 efs.internal:/ /net/efs 2>&1 ; \
                    mkdir -p \
                        /net/efs/preprocessing \
                        /net/efs/globalmodels \
                        /net/efs/globalscalers \
                    ; \
                "
            ],
            "readonlyRootFilesystem": False,
            "privileged": True
        }
    )
    print("Registered new job definition (revision {})".format(res['revision']))
    return res['jobDefinitionArn']


def get_latest_job_definition():
    res = batch_client.describe_job_definitions(jobDefinitionName='initialise-efs')
    revisions = sorted([(jd['revision'], jd['jobDefinitionArn']) for jd in res['jobDefinitions']])
    return revisions[-1][1]


def submit_job(job_definition_arn):
    print("Submitting job")
    res = batch_client.submit_job(
        jobName='initialise-efs',
        jobQueue='preprocessing-{}-compute'.format(args.environment),
        jobDefinition=job_definition_arn,
    )
    print("Job ID: {}".format(res['jobId']))
    return res['jobId']


def await_job(job_id):
    while True:
        job = batch_client.describe_jobs(jobs=[job_id])['jobs'][0]
        print("Job status: {}".format(job['status']))
        if job['status'] in ['FAILED']:
            raise Exception("Job failed!")
        elif job['status'] in ['SUCCEEDED']:
            print('Job complete')
            return
        else:
            print('Job still running')
            time.sleep(15)
            continue
    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Initialise a newly-created EFS filesystem')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('--no-register',
                        action='store_true',
                        dest='noregister',
                        help='Skip registering a new job definition, use the current latest one')

    args = parser.parse_args()
    batch_client = boto3.client('batch', region_name=args.region)

    if args.noregister:
        jd_arn = get_latest_job_definition()
    else:
        jd_arn = register_job_definition()
    print('Running job {}'.format(jd_arn))

    j_id = submit_job(jd_arn)
    await_job(j_id)
