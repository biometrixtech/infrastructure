# Installation

## Setting up a new environment / region

To set up a new environment, create a CloudFormation stack `preprocessing-<ENVIRONMENT>` in the region you want to deploy to.

The Elastic File System in the environment needs to be initialised with a directory structure.  This can be
achieved by registering a Batch Job as follows:

```shell
# TODO test this
aws batch register-job-definition \
    --job-definition-name initialise-efs \
    --type container \
    --container-properties '{ \
        "image": "python:2.7", \
        "vcpus": 1, \
        "memory": 128, \
        "command": [ \
            "/bin/bash", "-c", \
            " \
                apt-get update && apt-get install -y nfs-common ; \
                mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=10,retrans=2 efs.internal:/ /net/efs 2>&1 ; \
                mkdir \
                    /net/efs/downloadandchunk \
                    /net/efs/downloadandchunk\output \
                    /net/efs/sessionprocess2 \
                    /net/efs/sessionprocess2\output \
                    /net/efs/scoring \
                    /net/efs/scoring\output \
                    /net/efs/writemongo \
                ; \
                ln -s ../downloadandchunk/output /net/efs/sessionprocess2/input ; \
                ln -s ../sessionprocess2/output /net/efs/scoring/input ; \
                ln -s ../scoring/output /net/efs/writemongo/input ; \
            " \
        ] \
    }'
```

and then running the job on the compute cluster.
