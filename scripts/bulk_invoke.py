#!/usr/bin/python3
import argparse
import boto3
import datetime
import time


def invoke_lambda(s3_bucket, s3_key, timestamp):
    payload = '{"Records":[{"s3":{"bucket":{"name":"' + s3_bucket + '"},"object":{"key":"' + s3_key + '"}}, "eventTime": "' + timestamp + '"}]}'
    print(" " * 4 + s3_key)
    lambda_client.invoke(
        FunctionName='preprocessing-{}-ingest-trigger'.format(args.environment),
        Payload=payload,
    )


def process_file(s3_bucket, basename):
    for s3_file, last_modified in list_s3_files(s3_bucket, basename):
        invoke_lambda(s3_bucket, s3_file, last_modified.isoformat()[:-6] + 'Z')


def list_s3_files(s3_bucket, prefix, marker=''):
    ret = []
    resp = s3_client.list_objects(Bucket=bucket, Prefix=prefix, Marker=marker)
    ret.extend([(x['Key'], x['LastModified']) for x in resp['Contents'] if x['Key'][-8:] != 'combined'])
    if resp['IsTruncated']:
        ret.extend(list_s3_files(bucket, prefix, ret[-1]))
    return sorted(ret)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Invoke a test file')
    parser.add_argument('files',
                        type=str,
                        nargs='+',
                        help='The file(s) to run')
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
                        default='biometrix-preprocessing-{environment}-{region}')

    args = parser.parse_args()

    lambda_client = boto3.client('lambda', region_name=args.region)
    s3_client = boto3.client('s3')

    files = args.files
    bucket = args.bucket.format(environment=args.environment, region=args.region)

    count = 1
    for key in files:
        print('Invoking  {count}/{total} ({key})'.format(count=count, total=len(files), key=key))
        process_file(bucket, key)
        count += 1
