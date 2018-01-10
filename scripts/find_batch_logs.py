#!/usr/bin/env python
# Find the Batch logs for a particular execution
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



def get_boto3_client(resource):
    return boto3.client(
        resource,
        region_name=args.region,
    )


def list_jobs(queue, status, next_token=None):
    print('Finding Batch jobs')
    if next_token:
        res = batch_client.list_jobs(jobQueue=queue, jobStatus=status, nextToken=next_token)
    else:
        res = batch_client.list_jobs(jobQueue=queue, jobStatus=status)
    if 'nextToken' in res:
        return res['jobSummaryList'] + list_jobs(queue, status, res['nextToken'])
    else:
        return res['jobSummaryList']


def describe_jobs(jobs):
    print('Getting job details')
    job_details = []
    for sublist in [jobs[i:i + 100] for i in range(0, len(jobs), 100)]:
        res = batch_client.describe_jobs(jobs=sublist)
        job_details += res['jobs']
    return job_details


def main():
    all_jobs_with_status = list_jobs(args.queue, args.status)
    matching_jobs = [j for j in all_jobs_with_status if args.sensorfile in j['jobName'] and args.task in j['jobName']]
    job_details = describe_jobs([j['jobId'] for j in matching_jobs])

    jobs_by_startdate = []
    for job in job_details:
        task_id = job['attempts'][0]['container']['taskArn'].split('/')[-1]
        starttime = datetime.fromtimestamp(int(job['startedAt']) / 1000)
        url = 'https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logEventViewer:group=/aws/batch/job;stream=preprocessing-dev-batchjob/default/{task}'.format(
            region=args.region,
            queue=args.queue,
            task=task_id
        )
        jobs_by_startdate.append((starttime.isoformat(), url))

    for starttime, url in sorted(jobs_by_startdate, reverse=True)[:args.count]:
        print('{} --> {}'.format(starttime, url))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Search for the log output of a Batch job')
    parser.add_argument('--region', '-r',
                        type=str,
                        choices=['us-east-1', 'us-west-2'],
                        help='AWS Region')
    parser.add_argument('queue',
                        type=str,
                        help='The queue to search')
    parser.add_argument('sensorfile',
                        type=str,
                        help='Sensor file filter')
    parser.add_argument('task',
                        type=str,
                        help='Task filter')
    parser.add_argument('--status',
                        type=str,
                        choices=['SUCCEEDED', 'FAILED'],
                        default='SUCCEEDED',
                        help='Job status filter')
    parser.add_argument('--count',
                        type=int,
                        default=1,
                        help='How many results to return')

    args = parser.parse_args()
    batch_client = get_boto3_client('batch')
    main()
