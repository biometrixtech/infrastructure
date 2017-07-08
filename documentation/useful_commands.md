## Deployment

To start a CodeBuild build of the latest git revision

```shell
aws codebuild start-build \
	--project-name preprocessing-batchjob \
	--source-version `git rev-parse HEAD` | jq -r .build.id
```

To bump the version of a batch job used in a stack:
```shell
aws cloudformation deploy \
	--stack-name preprocessing-dev \
	--template-file /vagrant/Infrastructure/cloudformation/environment.template \
	--capabilities CAPABILITY_NAMED_IAM \
	--parameter-overrides BatchJobVersionScoring=23
```
