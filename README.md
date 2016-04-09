# github-snooze-button [![Build Status](https://travis-ci.org/tdsmith/github-snooze-button.svg?branch=master)](https://travis-ci.org/tdsmith/github-snooze-button) [![Coverage Status](https://coveralls.io/repos/github/tdsmith/github-snooze-button/badge.svg?branch=master)](https://coveralls.io/github/tdsmith/github-snooze-button?branch=master) [![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg)](https://raw.githubusercontent.com/tdsmith/github-snooze-button/master/LICENSE) [![PyPI](https://img.shields.io/pypi/v/github-snooze-button.svg)](https://pypi.python.org/pypi/github-snooze-button)


Projects with a lot of issue volume accumulate a lot of open issues which are not immediately actionable, usually because they're waiting for a response from a contributor. There's no easy way to hide those from the Github interface or signal to other maintainers that an open issue or PR isn't actionable yet.

Enter github-snooze-button!

Add a "snooze" label to an issue, and github-snooze-button will remove the label whenever

* an issue or pull request receives a comment,
* a pull request receives a comment on a diff, or
* a pull request branch is updated.

github-snooze-button can operate in two modes: deployed to AWS Lambda, or polling a Amazon SQS queue locally.

## Configuration file

github-snooze-button uses .ini-style configuration files that look like:

```
[default]
github_username = your_username
github_token = your_token
aws_key = your_key
aws_secret = your_secret
snooze_label = snooze
# aws_region = us-west-2 # optional

[your_username/repo1]

[your_username/repo2]
snooze_label = response required
```

The AWS credentials in the config file are sent to Github and used to push notifications into SNS. The listener also uses them to consume events from SQS. They are not used to configure the Lambda deployment.

## Option 1: AWS Lambda deployment

1. Generate a Github authentication token with `public_repo` and `admin:repo_hook` scopes. (Note that `public_repo` gives write permission! These credentials will be embedded in the Lambda deployment package, so you should consider the contents of the deployment package sensitive.)
1. Save AWS credentials with [these permissions or better](https://gist.github.com/c27412689c76d01968c86536df796a11) to a place boto can find them: either [in the environment](https://boto3.readthedocs.org/en/latest/guide/configuration.html#environment-variables) or in a [configuration file](https://boto3.readthedocs.org/en/latest/guide/configuration.html#shared-credentials-file).
1. Install github-snooze-button: `pip install git+https://github.com/tdsmith/github-snooze-button.git`
1. Launch with `snooze_deploy /path/to/config.ini`. `snooze_deploy` will:
    * Build deployment packages for each repository
    * Define or re-use a `/tdsmith/github-snooze-button/snooze_lambda_role` IAM role with the `AWSLambdaBasicExecutionRole` policy
    * Create or re-use SNS topics for each repository
    * Configure each Github repository to push notifications to SNS
    * Create or update a Lambda function for each repository
    * Give each SNS topic permission to invoke its matching Lambda function and create a subscription connecting them

And now you're live.

## Option 2: Polling mode

1. Generate a Github authentication token with `public_repo` and `admin:repo_hook` scopes.
1. In AWS IAM, create a Amazon AWS user with all the AmazonSQS* and AmazonSNS* policies (and possibly fewer?)
1. Install github-snooze-button: `pip install git+https://github.com/tdsmith/github-snooze-button.git`
1. Launch with `snooze_listen /path/to/config.ini`

Note that the queue will continue collecting events unless you disconnect the repository from SNS.

## Teardown

The fastest way to disable github-snooze-button is by deleting the Amazon SNS service from your repository's "Webhooks & services" configuration page. It will be automatically recreated the next time you run snooze in either mode.

## Questions

* _Will this cost me lots of money?_
  Probably not. Lambda, [SNS](https://aws.amazon.com/sns/pricing/) and [SQS](https://aws.amazon.com/sqs/pricing/) are both free for the first million transactions a month. Homebrew uses a few hundred transactions a day. YMMV!

## Contact

Tim D. Smith: snooze at tds.xyz, Freenode: tdsmith, @biotimylated
