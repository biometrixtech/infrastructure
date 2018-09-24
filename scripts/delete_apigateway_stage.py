#! /usr/bin/env python3

import argparse
import boto3
from colorama import Fore
from semver import VersionInfo

from components.ui import cprint, confirm
from components.api_gateway import ApiGateway
from components.exceptions import ApplicationException
from components.lambda_function import LambdaFunction


def main():

    if args.environment == 'production':
        cprint('Are you sure you want to deploy to production?! (y/n)', colour=Fore.YELLOW)
        if not confirm():
            exit(0)

    lambda_function = LambdaFunction(
        region_name=args.region,
        environment_name=args.environment,
        service_name=args.service,
        function_name=f'{args.service}-{args.environment}-apigateway-execute',
        s3_filepath='apigateway.zip'
    )
    api_gateway = ApiGateway(f'{args.service}-{args.environment}-apigateway', lambda_function)

    for version in args.version:
        api_gateway.delete_stage(version)
        lambda_function.delete_alias(version)


if __name__ == '__main__':
    def validate_semver(value):
        try:
            return VersionInfo.parse(value)
        except Exception:
            raise argparse.ArgumentTypeError('Not a valid semantic version')

    parser = argparse.ArgumentParser(description='Deploy a new version of a service to an environment')
    parser.add_argument('--region',
                        choices=['us-west-2'],
                        default='us-west-2',
                        help='AWS Region')
    parser.add_argument('environment',
                        choices=['dev', 'test', 'production'],
                        help='Environment')
    parser.add_argument('service',
                        choices=[
                            'hardware',
                            'meta',
                            'plans',
                            'preprocessing',
                            'statsapi',
                            'time',
                            'users',
                        ],
                        help='The service being affected')

    parser.add_argument('version',
                        help='The semantic versions to delete',
                        nargs='+',
                        type=validate_semver)

    parser.add_argument('--profile-name',
                        dest='profile_name',
                        default='default',
                        help='boto3 profile to use')

    args = parser.parse_args()

    boto3.setup_default_session(profile_name=args.profile_name, region_name=args.region)

    try:
        main()
    except KeyboardInterrupt:
        cprint('Exiting', colour=Fore.YELLOW)
        exit(1)
    except ApplicationException as ex:
        cprint(str(ex), colour=Fore.RED)
        exit(1)
    except Exception as ex:
        cprint(str(ex), colour=Fore.RED)
        raise ex
    else:
        exit(0)
