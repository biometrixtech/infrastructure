#!/usr/bin/env bash

# Directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

docker run \
   -v ${DIR}/../..:/vagrant \
   -v ~/.ssh:/home/biometrix/.ssh \
   -v ~/.gitignore:/home/biometrix/.gitignore \
   -it \
   --name biometrixtech \
   -u biometrix \
   --rm \
   biometrixtech:latest