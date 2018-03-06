#!/usr/bin/env python3
# Get a matrix of daily spends by Project and Environment
# Copyright 2018 Melon Software Ltd (UK).  Used under license
from __future__ import print_function
from datetime import datetime
import argparse
import boto3
import pandas as pd


def main():
    # TODO optional start/end date
    res = ce_client.get_cost_and_usage(
        TimePeriod={'Start': args.start, 'End': args.end},
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'TAG','Key': 'Project'}, {'Type': 'TAG', 'Key': 'Environment'}]
    )['ResultsByTime']

    matrix = {}
    for day in res:
        for group in day['Groups']:
            project = group['Keys'][0].split('$')[-1]
            environment = group['Keys'][1].split('$')[-1]
            if project not in matrix:
                matrix[project] = {}
            if environment not in matrix[project]:
                matrix[project][environment] = []
            matrix[project][environment].append(float(group['Metrics']['UnblendedCost']['Amount']))

    for row in matrix:
        for column in matrix[row]:
            matrix[row][column] = sum(matrix[row][column]) / len(matrix[row][column])

    matrix_pd = pd.DataFrame(matrix).T
    matrix_pd.fillna(0, inplace=True)
    print(matrix_pd.round(2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Search for the log output of a Batch job')
    parser.add_argument('--start',
                        type=str,
                        # default='',
                        help='Start date')
    parser.add_argument('--end',
                        type=str,
                        # default='',
                        help='End date')

    args = parser.parse_args()
    ce_client = boto3.client('ce', region_name='us-east-1')  # Cost Explorer is only in Virginia
    main()
