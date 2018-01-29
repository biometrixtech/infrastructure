#!/usr/bin/env python
# Stop all executions in a given SFN State Machine, to allow it to be deleted
import json

import boto3
import argparse


def get_executions(state_machine_id, status='RUNNING'):
    state_machine_arn = 'arn:aws:states:{}:887689817172:stateMachine:{}'.format(args.region, state_machine_id)
    res = stepfunctions_client.list_executions(stateMachineArn=state_machine_arn, statusFilter=status)
    return [execution['executionArn'] for execution in res['executions']]


def stop_execution(execution_arn):
    stepfunctions_client.stop_execution(executionArn=execution_arn, error='CANCELLED', cause=args.cause)


def purge_linearity_queue():
    print('Purging linearity enforcing queue')
    queue = boto3.resource('sqs').Queue('https://sqs.{}.amazonaws.com/887689817172/preprocessing-{}-linearity.fifo'.format(args.region, args.environment))
    queue.purge()
    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Stop all executions in a given SFN State Machine, to allow it to be deleted')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('--cause',
                        type=str,
                        help='The reason for stopping',
                        default='State Machine is being deleted')

    args = parser.parse_args()
    stepfunctions_client = boto3.client('stepfunctions', region_name=args.region)

    running_executions = get_executions('preprocessing-{}'.format(args.environment))

    for i, execution in enumerate(running_executions):
        print("Stopping execution {}/{}".format(i + 1, len(running_executions)))
        stop_execution(execution)

    purge_linearity_queue()
