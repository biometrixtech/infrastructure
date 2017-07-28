#!/usr/bin/env python
# Set configuration values in SSM
import boto3
import argparse


def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def load_parameters(keys, environment):
    if len(keys) > 0:
        print('Retrieving configuration for [{}] from SSM'.format(", ".join(keys)))
        ssm_client = boto3.client('ssm')

        for key_batch in chunk_list(keys, 10):
            response = ssm_client.get_parameters(
                Names=['preprocessing.{}.{}'.format(environment, key.lower()) for key in key_batch],
                WithDecryption=True
            )
            for p in response['Parameters']:
                yield (p['Name'].split('.')[-1].lower(), p['Value'])


def set_parameters(keys):
    if len(keys) == 0:
        return

    print('Setting configuration values for [{}] to SSM'.format(", ".join(keys)))
    ssm_client = boto3.client('ssm', region_name=args.region)

    for key, value in keys.items():
        ssm_client.put_parameter(
            Name='preprocessing.{}.{}'.format(args.environment, key.lower()),
            Value=value,
            Type='SecureString',
            KeyId='alias/preprocessing/{}'.format(args.environment),
            Overwrite=True,
        )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Set configuration in SSM')
    parser.add_argument('configs',
                        type=str,
                        nargs='*',
                        help='The values to set, as key=value pairs')
    parser.add_argument('--environment', '-e',
                        type=str,
                        help='Environment')
    parser.add_argument('--region', '-r',
                        type=str,
                        help='AWS Region')
    parser.add_argument('--copy-from-environment',
                        dest='copy_from_environment',
                        type=str,
                        help='Environment to copy values from')

    args = parser.parse_args()

    if not args.environment:
        print("Must specify an environment")
        exit(1)
    if not args.region:
        print("Must specify a region")
        exit(1)

    config_values = {c.split('=', 1)[0]: c.split('=', 1)[-1] for c in args.configs}

    if args.copy_from_environment:
        print("Copying values from {} environment".format(args.copy_from_environment))
        for key, value in load_parameters(config_values.keys(), args.copy_from_environment):
            config_values[key] = value

    set_parameters(config_values)