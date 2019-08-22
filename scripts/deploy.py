#!/usr/bin/env python3
# Upload a cloudformation template to S3, then run a stack update
from botocore.exceptions import ClientError
from colorama import Fore
from semver import VersionInfo
import argparse
import boto3

from components.environment import Environment, LegacyEnvironment
from components.exceptions import ApplicationException
from components.ui import confirm, cprint


def map_config(old_config):
    """
    Create the new config
    :param dict old_config:
    :return: dict
    """
    param_renames = dict([a.split('->') for a in filter(None, args.param_renames.split(','))])
    param_updates = dict([a.split('->') for a in filter(None, args.param_updates.split(','))])

    new_config = {}

    # Rename parameters
    for old_key, new_key in param_renames.items():
        if old_key not in old_config:
            raise ApplicationException(f'{old_key} not found in existing config, cannot rename')

        if new_key == '':
            cprint(f'Removing parameter {old_key}')
        else:
            cprint(f'Renaming parameter {old_key} to {new_key}')
            new_config[new_key] = old_config[old_key]

        new_config[old_key] = NotImplemented

    # Set new parameter values
    for key, value in param_updates.items():
        cprint(f'Setting parameter {key} to "{value}"')
        new_config[key] = value

    return new_config


def validate_semver_tag(new_tag, old_tags):
    """
    Check for various version consistency gotchas
    :param VersionInfo new_tag:
    :param list[VersionInfo] old_tags:
    :return:
    """
    for old_tag in old_tags:
        if old_tag == new_tag:
            raise ApplicationException(f'Release {args.service}:{new_tag} already exists. To roll back to a previous version, run [deploy.py {args.environment} {args.service} --ref {new_tag}]')
        elif old_tag > new_tag:
            if old_tag.major != new_tag.major:
                # It's ok to prepare a legacy release
                pass
            elif old_tag.minor != new_tag.minor:
                # It's ok to patch an old minor release when a new minor release exists
                pass
            elif args.force:
                cprint(f"Shouldn't be releasing {args.service}:{new_tag} because a later version {old_tag} already exists.", colour=Fore.RED)
            else:
                raise ApplicationException(f'Cannot release {args.service}:{new_tag} because a later version {old_tag} already exists.')

    # Prevent skipping versions
    previous_tag = get_previous_semver(new_tag)
    for old_tag in old_tags:
        if old_tag >= previous_tag:
            break
    else:
        if args.force:
            cprint(f"Shouldn't be releasing {args.service}:{new_tag} because it skips (at least) version {previous_tag}.", colour=Fore.RED)
        else:
            raise ApplicationException(f'Cannot release {args.service}:{new_tag} because it skips (at least) version {previous_tag}.')

    if args.environment == 'production' and new_tag.prerelease is not None:
        raise ApplicationException('Pre-release versions (ie with build suffixes) cannot be deployed to production')


def get_previous_semver(v: VersionInfo) -> VersionInfo:
    """
    Return a semantic version which is definitely less than the target version
    :param VersionInfo v:
    :return: VersionInfo
    """
    if v.build is not None:
        raise Exception(f'Cannot calculate previous version because {v} has a build number')

    if v.prerelease is not None:
        prerelease_parts = v.prerelease.split('.')
        if prerelease_parts[-1].isdigit() and int(prerelease_parts[-1]) > 1:
            return VersionInfo(v.major, v.minor, v.patch, prerelease_parts[0] + '.' + str(int(prerelease_parts[-1]) - 1))

    if v.patch > 0:
        return VersionInfo(v.major, v.minor, v.patch - 1)

    if v.minor > 0:
        return VersionInfo(v.major, v.minor - 1, 0)

    if v.major > 0:
        return VersionInfo(v.major - 1, 0, 0)

    raise Exception(f'Could not calculate a previous version for {v}')


def main():

    if args.environment in ['dev', 'production']:
        environment = LegacyEnvironment(args.region, args.environment, args.service)
        service_repository = environment.get_service_repository(args.service)

        if args.environment_version != '':
            raise ApplicationException('--environment_version parameter is not compatible with legacy environments')
        environment_version = None

    else:
        environment = Environment(args.region, args.environment)
        service_repository = environment.get_service_repository(args.service)
        if args.environment_version != '':
            environment_version = environment.repository.parse_ref(args.environment_version)[0]
            # Check that the build we're about to deploy has actually been completed
            environment.repository.await_build_completion(environment_version)
        else:
            environment_version = None

    if args.ref is None:
        if args.environment == 'production':
            args.ref = 'master'
        else:
            args.ref = f'{args.environment}-master'

    service_version, ref_type = service_repository.parse_ref(args.ref)

    if args.tag is None:
        if args.environment == 'dev':
            # It's ok to not tag versions in dev
            version = None
        elif ref_type == 'tag':
            # Deploying from a tag, could be a rollback
            version = None
        elif args.force:
            cprint(f"Deployments to environments above dev should be tagged", colour=Fore.RED)
            version = None
        else:
            raise ApplicationException('Deployments to environments above dev must be tagged')
    else:
        version = VersionInfo.parse(args.tag)
        validate_semver_tag(version, service_repository.get_semver_tags())

    #             | head                  | commit    | branch                  | tag
    #  -----------+-----------------------+-----------+-------------------------+-----
    #  dev        | upload_working_copy() | Ok        | compare_remote_status() | Ok
    #  test       | X                     | confirm() | compare_remote_status() | confirm()
    #  <other>    | X                     | confirm() | compare_remote_status() | confirm()
    #  production | X                     | confirm() | compare_remote_status() | confirm()

    # Do the pre-upload of templates to the 00000000 version
    if ref_type == 'head':
        if args.environment == 'dev':
            service_repository.upload_working_copy()
        else:
            raise ApplicationException('Working copy can only be deployed to dev')

    if ref_type == 'branch':
        comparison = service_repository.compare_remote_status(args.ref)
        if comparison == -1:
            if not confirm(f'Branch {args.ref} is behind origin/{args.ref}.  Are you sure you want to deploy an earlier version?'):
                exit(0)
        elif comparison == 1:
            raise ApplicationException(f'Branch {args.ref} is ahead of origin/{args.ref}.  You need to push your changes')

    if version is not None:
        cprint(f"Going to tag commit {service_version[0:16]} (from {ref_type} {args.ref}) as {version} and deploy to {args.environment}", colour=Fore.YELLOW)
    else:
        cprint(f"Going to deploy commit {service_version[0:16]} (from {ref_type} {args.ref}) to {args.environment}", colour=Fore.YELLOW)

    if not args.yes and (args.environment != 'dev' or version is not None):
        if not confirm('Is this what you wanted? '):
            exit(0)

    if args.environment == 'production':
        cprint('Are you sure you want to deploy to production?! (y/n)', colour=Fore.YELLOW)
        if not confirm():
            exit(0)

    if version is not None:
        service_repository.create_semver_tag(version, service_version)

    # Check that the build we're about to deploy has actually been completed
    service_repository.await_build_completion(service_version)

    try:
        # Actually update the service
        environment.update_config(map_config(environment.config))
        environment.update_environment_version(environment_version)
        environment.update_service_version(args.service, service_version)
        environment.update()
    except ClientError as e:
        if ref_type == 'tag':
            # Delete the tag
            service_repository.delete_tag(version)

        if 'No updates are to be performed' in str(e):
            cprint('No updates are to be performed', colour=Fore.YELLOW)
        elif 'is in UPDATE_IN_PROGRESS state' in str(e):
            cprint('Stack is already updating', colour=Fore.YELLOW)
            environment.await_deployment_complete()
        else:
            cprint(e, colour=Fore.RED)
        exit(1)

    environment.await_deployment_complete()

    if service_repository.git_repo_name != 'infrastructure':
        # Update git reference
        cprint('Updating git reference')
        service_repository.update_git_branch(f'{args.environment}-{args.region}', service_version)

    if version is not None:
        # Create versions and aliases of lambda functions and set up a stage in API Gateway
        environment.update_lambda_functions(args.service, ref=service_version, tag=version)
        environment.create_apigateway_stages(args.service, version)

        # 'slide' the partially-pinned aliases up to the new version
        environment.update_sliding_lambda_aliases(args.service, version)

    else:
        # Explicitly deploy lambda functions anyway to make sure the $LATEST version is up to date
        environment.update_lambda_functions(args.service, ref=service_version)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Deploy a new version of a service to an environment')
    parser.add_argument('--region',
                        choices=['us-west-2'],
                        default='us-west-2',
                        help='AWS Region')
    parser.add_argument('environment',
                        choices=['dev', 'test', 'production', 'public'],
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
                        help='The service being deployed')

    parser.add_argument('--ref',
                        help='the branch or commit to deploy from',
                        default=None)

    parser.add_argument('--tag',
                        help='the tag to assign to the deployed version of the service',
                        default=None)

    parser.add_argument('--environment-version',
                        dest='environment_version',
                        default='',
                        help='The version of the whole-environment template to deploy')

    parser.add_argument('--param-renames',
                        dest='param_renames',
                        default='',
                        help='Parameters to rename ("oldparamname->newparamname,...") or drop ("oldparamname->,...")')
    parser.add_argument('--param-updates',
                        dest='param_updates',
                        default='',
                        help='Parameters to set new values for ("paramname->newvalue,...")')

    parser.add_argument('--profile-name',
                        dest='profile_name',
                        default='default',
                        help='boto3 profile to use')
    parser.add_argument('-y',
                        dest='yes',
                        action='store_true',
                        help='Skip confirmations')
    parser.add_argument('-f', '--force',
                        dest='force',
                        action='store_true',
                        help='Override validation')

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
