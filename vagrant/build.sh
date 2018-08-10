#!/usr/bin/env bash


# Directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

USER_NAME=''
USER_EMAIL=''
source ${DIR}/config.env
USER_ID=$( id -u )

# Remove any old container
docker rm biometrixtech-build 2> /dev/null

# Build a new one
docker run \
   -v ${DIR}/../..:/vagrant \
   -w /vagrant/infrastructure/vagrant \
   --name biometrixtech-build \
   -u root \
   geerlingguy/docker-ubuntu1804-ansible:latest \
   ansible-playbook ansible/main.yml -c local --extra-vars "user_uid='${USER_ID}' user_name='${USER_NAME}' user_email='${USER_EMAIL}'" \
&& docker commit \
   -c 'CMD ["ssh-agent", "bash"]' \
   biometrixtech-build \
   biometrixtech:latest \

docker rm biometrixtech-build > /dev/null