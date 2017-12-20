# Using the Vagrant box for development

## Setup
### Windows
* Install a few pieces of software on your machine:
  * [Vagrant](https://www.vagrantup.com/)
  * [Virtual Box](https://www.virtualbox.org/)
  * [PuTTY, PuTTYGen and Pageant](https://www.chiark.greenend.org.uk/~sgtatham/putty/)
* Create a directory for the project and clone the various repositories into it.  Create empty directories for any repos that you don't need.  You must create folders for the following repositories:
  * Alerts
  * Infrastructure
  * PreProcessing
  * Users
  * Website
* Choose a username for yourself; eg John Smith might choose `jsmith`
* Using Pageant, create a new SSH private key or load an existing one, then copy the contents of the "Public key for pasting into OpenSSH authorized_keys file" into `/YOURFOLDER/Infrastructure/vagrant/ansible/authorized_keys/YOURUSERNAME.azk`
* Open a command prompt, and run the commands
  * `cd /YOURFOLDER/Infrastructure/vagrant`
  * `vagrant --port-suffix=11 up`, changing the `port-suffix` value if necessary if port 2211 is already in use on your machine.
* Leave to run - this will take a while the first time you do it as it installs various packages in a self-contained virtual environment.
* Once finished, open PuTTY and connect to `YOURUSERNAME@localhost` on port `2211`.

## Usage
The vagrant environment is set up with a number of useful development tools, including:
* `aws` the AWS CLI
* `aws-mfa` simplifying using AWS IAM credentials which require multi-factor authentication
* `docker` including the ECR credential helper
* `git`
* `packer`
* `python` 2.7 and 3.6
* `ruby`
