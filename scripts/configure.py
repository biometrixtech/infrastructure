#!/usr/bin/env python
# Set configuration values in SSM
import boto3
import argparse


def chunk_list(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def get_all_ssm_keys(environment, region, next_token=None):
    ssm_client = boto3.client('ssm', region_name=region)
    if next_token is not None:
        response = ssm_client.describe_parameters(
            ParameterFilters=[{'Key': "Name", 'Values': ["preprocessing.{}.".format(environment)], 'Option': "BeginsWith"}],
            MaxResults=50,
            NextToken=next_token,
        )
    else:
        response = ssm_client.describe_parameters(
            ParameterFilters=[{'Key': "Name", 'Values': ["preprocessing.{}.".format(environment)], 'Option': "BeginsWith"}],
            MaxResults=50
        )
    return [p['Name'] for p in response['Parameters']] + (get_all_ssm_keys(environment, region, response['NextToken']) if 'NextToken' in response else [])


def load_parameters(keys, environment, region):
    print('Retrieving configuration for [{}] from SSM'.format(", ".join(keys)))
    ssm_client = boto3.client('ssm', region_name=region)

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


def main():

    if not args.environment:
        print("Must specify an environment")
        return
    if not args.region:
        print("Must specify a region")
        return
    cf_environment = args.copy_from_environment or args.environment
    cf_region = args.copy_from_region or args.region

    if len(args.configs) == 0:
        print('Must specify a configuration key to set, or "*" to copy all keys')
        return
    elif len(args.configs) == 1 and args.configs[0] == '*':
        if args.copy_from_environment:
            print("Listing keys from {}/{} environment".format(cf_region, cf_environment))
            keys = [k.split('.')[-1] for k in get_all_ssm_keys(args.copy_from_environment, cf_region)]
            config_values = {k: '' for k in keys}
        else:
            print('Must specify --copy-from-region to load all keys')
            return
    else:
        config_values = {c.split('=', 1)[0].lower(): c.split('=', 1)[-1] for c in args.configs}

    if args.copy_from_environment or args.copy_from_region:
        print("Copying values from {}/{} environment".format(cf_region, cf_environment))
        for key, value in load_parameters(config_values.keys(), cf_environment, cf_region):
            config_values[key] = value

    set_parameters(config_values)


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
    parser.add_argument('--copy-from-region',
                        dest='copy_from_region',
                        type=str,
                        help='Region to copy values from')

    args = parser.parse_args()
    main()
