from boto3.dynamodb.conditions import Key, Attr
from colorama import Fore
from semver import VersionInfo
from subprocess import CalledProcessError
import boto3
import json
import os
import re
import subprocess
import time

from components.exceptions import ApplicationException
from components.ui import cprint, Spinner

lambci_builds_table = boto3.resource('dynamodb', region_name='us-east-1').Table('infrastructure-lambci-builds')

# https://github.com/semver/semver/issues/232#issuecomment-405596809
semver_regex = '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'


class Repository(object):
    def __init__(self, service):
        self.service = service
        self._git_dir = self._get_git_dir()

    @property
    def git_repo_name(self):
        if self.service in ['time', 'meta']:
            return 'infrastructure'
        return self.service

    def upload_working_copy(self):
        """
        Upload the resources currently in the working copy to S3 under the '00000000' commit hash
        """
        # TODO
        raise NotImplementedError()

    def get_build_number_for_version(self, version):
        """
        Get the LambCI build number corresponding to a particular version
        :param str version:
        :return: str
        """
        builds = lambci_builds_table.query(
            KeyConditionExpression=Key('project').eq(self.lambci_project_name),
            FilterExpression=Attr('commit').eq(version),
            ScanIndexForward=False,
        )['Items']
        if len(builds) == 0:
            raise ApplicationException(f'No build has been started for {version}.  Have you pushed your changes?')
        elif len(builds) > 1:
            cprint(f'Multiple builds found for version {version}, using most recent', colour=Fore.YELLOW)
            return max([b['buildNum'] for b in builds])
        else:
            return builds[0]['buildNum']

    def get_build_status(self, build_number):
        """
        Check the status of the LambCI build for a given version, by querying the `infrastructure-lambci-builds`
        DynamoDB table.

        :param str build_number: The build_number to check
        :return: str
        """
        kcx = Key('project').eq(self.lambci_project_name) & Key('buildNum').eq(build_number)
        builds = lambci_builds_table.query(KeyConditionExpression=kcx)['Items']
        if len(builds) == 0:
            raise ApplicationException('Unrecognised build number')
        else:
            return builds[0]['status']

    def await_build_completion(self, version):
        """
        Wait until the LambCI build for a given git version has completed

        :param str version: The full commit hash of the version to check
        """
        spinner = Spinner()
        try:
            counts = 12
            build_number = self.get_build_number_for_version(version)
            cprint(f'Waiting for CI build completion for {version} (#{build_number}) ', colour=Fore.CYAN, end="")
            spinner.start()

            while counts >= 0:
                build_status = self.get_build_status(build_number)

                if build_status == 'success':
                    cprint("\b \r\nBuild complete                        ", colour=Fore.GREEN)
                    break

                else:
                    counts -= 1
                    time.sleep(5)
                    continue
            else:
                cprint("\b \r\nBuild not completed after 60 seconds                        ", colour=Fore.RED)
                exit(1)

        finally:
            spinner.stop()
            cprint('')

    def parse_ref(self, version):
        """
        Convert a free-form git reference (full or partial commit hash, branch or tag name, or the special string of
        at least eight zeroes) into a full commit hash and type

        :param str version: The git reference to parse
        :return: (str, str)
        """
        if re.match('^0{8,}$', version):
            # All zeroes = working copy
            cprint('Deploying working copy', colour=Fore.YELLOW)
            return '0' * 40, 'head'

        elif re.match('^[0-9a-f]{40}$', version):
            # Already a full commit hash
            try:
                self._execute_git_command(f'git branch --contains {version}')
                return version, 'commit'
            except CalledProcessError:
                raise ApplicationException(f'Commit {version} does not exist')

        elif version == 'HEAD':
            try:
                version = self._execute_git_command(f'git rev-parse HEAD')
                return version, 'head'
            except CalledProcessError:
                raise ApplicationException(f'Commit {version} does not exist')

        else:
            try:
                # Parse the value as a branch name and get the associated git commit hash
                x2 = self._execute_git_command(f'git show-ref --verify refs/tags/{version}', True).split(' ')[0]
                cprint(f"Tag '{version}' has commit hash {x2}", colour=Fore.GREEN)
                return x2, 'tag'
            except CalledProcessError:
                try:
                    # Parse the value as a branch name and get the associated git commit hash
                    x2 = self._execute_git_command(f'git show-ref --verify refs/heads/{version}', True).split(' ')[0]
                    cprint(f"Branch '{version}' has commit hash {x2}", colour=Fore.GREEN)
                    return x2, 'branch'
                except CalledProcessError:
                    raise ApplicationException('Version must be a 40-hex-digit git hash or valid branch or tag name')

    def compare_remote_status(self, branch_name):
        """
        Check whether the local version of a branch is behind, level with or ahead of the remote
        :param str branch_name:
        :return: int
        """
        # Update remotes first
        self._execute_git_command('git remote update')

        return self.compare_refs(branch_name, f'origin/{branch_name}')

    def compare_refs(self, ref1, ref2):
        """
        Check whether one git ref is behind, equal to or ahead of another
        :param str ref1:
        :param str ref2:
        :return: int
        """

        local_ref = self._execute_git_command(f'git rev-parse {ref1}')

        remote_ref = self._execute_git_command(f'git rev-parse {ref2}')

        # The first common ancestor of the local and remote branches
        parent_ref = self._execute_git_command(f'git merge-base {ref1} {ref2}')

        if local_ref == remote_ref:
            return 0  # Branches are equal
        elif local_ref == parent_ref:
            return -1  # The remote is ahead of local
        elif remote_ref == parent_ref:
            return 1  # The local ref is ahead of remote
        else:
            raise ApplicationException(f'Branch {ref1} has diverged from {ref2}')

    def update_git_branch(self, branch_name, version):
        """
        Move a branch pointer to a particular commit

        :param str branch_name: The branch to update
        :param str version: The commit hash of the commit to move to
        """
        try:
            self._execute_git_command(f"git update-ref refs/heads/{branch_name} {version}")
            self._execute_git_command(f"git push origin {branch_name} --force")
        except CalledProcessError:
            cprint('Could not update git branch references.  Are your SSH keys set up properly?', colour=Fore.RED)

    def get_config(self):
        with open(os.path.join(self._git_dir, 'resource_index.json'), 'r') as f:
            config = json.load(f)
            return config

    def get_semver_tags(self):
        def make_semver(tag):
            try:
                return VersionInfo.parse(tag)
            except ValueError:
                return None

        all_tags = self._execute_git_command(f'git tag')
        return list(filter(None, [make_semver(tag) for tag in all_tags.split('\n')]))

    def create_semver_tag(self, tag, ref):
        self._execute_git_command(f"git tag {tag} {ref}")
        self._execute_git_command(f'git push origin {tag}')

    def _get_git_dir(self):
        try:
            return os.path.realpath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), f'../../../{self.git_repo_name}'))
        except KeyError:
            raise ApplicationException(f'No Git repository configured for service {self.service}')

    def _execute_git_command(self, command, suppress_errors=False):
        stderr = subprocess.DEVNULL if suppress_errors else subprocess.STDOUT
        return subprocess.check_output(command, cwd=self._git_dir, shell=True, stderr=stderr).decode('utf-8').strip()

    @property
    def lambci_project_name(self):
        # Capitalisation of Github repositories (which is inconsistent boo hiss) is preserved in the project key here
        repository_names = {
            'hardware': 'Hardware',
            'infrastructure': 'infrastructure',
            'plans': 'plans',
            'preprocessing': 'PreProcessing',
            'users': 'Users',
        }
        return f'gh/biometrixtech/{repository_names[self.service]}'
