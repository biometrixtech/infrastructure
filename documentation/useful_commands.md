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

To deploy a new version of the Pipeline to an environment
```shell
STACK_NAME=aws cloudformation describe-stack-resource --stack-name preprocessing-dev --logical-resource-id PipelineCluster | jq -r '.StackResourceDetail.PhysicalResourceId | split("/")[1]'`
scripts/deploy_cloudfromation.py \
	--region us-west-2 \
	--service preprocessing \
	--environment <env> \
	--service pipeline \
	$STACK_NAME	
```
