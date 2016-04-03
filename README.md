# github-snooze-button [![Build Status](https://travis-ci.org/tdsmith/github-snooze-button.svg?branch=master)](https://travis-ci.org/tdsmith/github-snooze-button) [![Coverage Status](https://coveralls.io/repos/github/tdsmith/github-snooze-button/badge.svg?branch=master)](https://coveralls.io/github/tdsmith/github-snooze-button?branch=master) [![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg)](https://raw.githubusercontent.com/tdsmith/github-snooze-button/master/LICENSE)


Projects with a lot of issue volume accumulate a lot of open issues which are not immediately actionable, usually because they're waiting for a response from a contributor. There's no easy way to hide those from the Github interface or signal to other maintainers that an open issue or PR isn't actionable yet.

Enter github-snooze-button!

Add a "snooze" label to an issue, and github-snooze-button will remove the label whenever

* an issue or pull request receives a comment,
* a pull request receives a comment on a diff, or
* a pull request branch is updated.

## Setup

1. Generate a Github authentication token with `public_repo` and `admin:repo_hook` scopes.
1. In AWS IAM, create a Amazon AWS user with all the AmazonSQS* and AmazonSNS* policies (and possibly fewer?)
1. Create a INI-style configuration file that looks like:
    ```
    [default]
    github_username = your_username
    github_token = your_token
    aws_key = your_key
    aws_secret = your_secret
    # aws_region = us-west-2 # optional

    [your_username/repo1]

    [your_username/repo2]
    ```
1. Install github-snooze-button: `pip install git+https://github.com/tdsmith/github-snooze-button.git`
1. Launch with `python -m snooze /path/to/config.ini`

## Questions

* _Will this cost me lots of money?_ 
  Probably not. [SNS](https://aws.amazon.com/sns/pricing/) and [SQS](https://aws.amazon.com/sqs/pricing/) are both free for the first million transactions a month. YMMV!

## Contact

Tim D. Smith: snooze at tds.xyz, Freenode: tdsmith, @biotimylated
