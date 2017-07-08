#!/usr/bin/python3
import argparse
import boto3
import time


def invoke_sfn(s3_bucket, s3_key):
    lambda_client = boto3.client('lambda', region_name=args.region)
    lambda_client.invoke(
        FunctionName='preprocessing-{}-pipeline-trigger'.format(args.environment),
        Payload='{"Records":[{"s3":{"bucket":{"name":"' + s3_bucket + '"},"object":{"key":"' + s3_key + '"}}}]}',
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Invoke one or more test files')
    parser.add_argument('files',
                        type=str,
                        help='The files to run with',
                        nargs='+')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region',
                        default='us-west-2')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment',
                        default='dev')
    parser.add_argument('--bucket', '-b',
                        type=str,
                        help='S3 bucket',
                        default='biometrix-testdatav2')
    parser.add_argument('--delay', '-d',
                        type=int,
                        help='Delay between invocations (secs)',
                        default=0)

    args = parser.parse_args()

    count = 1
    for key in args.files:
        print('Invoking  {count}/{total} ({key})'.format(count=count, total=len(args.files), key=key))
        invoke_sfn(args.bucket, key)
        time.sleep(args.delay)
        count += 1
