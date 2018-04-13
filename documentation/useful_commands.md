## Deployment

To start a CodeBuild build of the latest git revision (if not working automatically for some reason)

```shell
aws codebuild start-build \
	--project-name preprocessing-batchjob \
	--source-version `git rev-parse HEAD` | jq -r .build.id
```

To deploy a new job version to the preprocessing pipeline:
```shell
scripts/deploy_newversion.py \
	--region us-west-2 \
	--environment dev \
	<GIT_VERSION>
```

To deploy a new version of a service to an environment:
```shell
scripts/deploy_service.py <service> <environment> environment <version>
```

Where `version` must be a 40-hex-digit Git hash.
