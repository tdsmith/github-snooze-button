from __future__ import absolute_import

import argparse
import glob
import logging
import os
import shutil
import subprocess as sp
import sys
import tempfile
from textwrap import dedent

import boto3
from botocore.exceptions import ClientError
import pkg_resources

import snooze


LAMBDA_ROLE_TRUST_POLICY = """\
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
"""


def create_or_get_lambda_role():
    """Creates the Lambda execution role for github-snooze-button.

    Args: None
    Returns: None
    """
    lambda_role_path = "/tdsmith/github-snooze-button/"
    lambda_role_name = "snooze_lambda_role"

    iam = boto3.resource("iam")
    roles = iam.roles.all()
    for role in roles:
        if role.path == lambda_role_path and role.name == lambda_role_name:
            return role

    role = iam.create_role(
        Path=lambda_role_path,
        RoleName=lambda_role_name,
        AssumeRolePolicyDocument=LAMBDA_ROLE_TRUST_POLICY)
    role.attach_policy(
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    return role


def create_deployment_packages(config):
    """Builds deployment packages for each configured repository.

    This function does not touch AWS. Deployment packages are saved as .zip
    files in the current working directory. The filenames of the deployment
    packages are saved as "zip_filename" keys on the config object.

    Assumes that `zip` exists in PATH and `pip` is installed to the current
    environment.

    Args:
        config (dict): Configuration dictionary from parse_config. Modified
            in-place by addition of a "zip_filename" key.

    Returns: None
    """
    # get the list of packages snooze requires
    dist = pkg_resources.get_distribution("github-snooze-button")
    requires = [str(i) for i in dist.requires()]

    # Amazon provides boto3
    requires = [i for i in requires if not i.startswith("boto3")]

    tmpdir = tempfile.mkdtemp()
    try:
        devnull = open(os.devnull, "w")
        sp.check_call([
            sys.executable, "-m", "pip",
            "install",
            "--target", tmpdir] + requires,
            stdout=devnull, stderr=sp.STDOUT)
        shutil.copytree(
            os.path.dirname(__file__),
            os.path.join(tmpdir, "snooze"))
        shutil.copy(
            os.path.join(os.path.dirname(__file__), "lambda_handler.py"),
            tmpdir
        )
        for repository_name, repo in config.items():
            logging.info("Building deployment package for %s" % repository_name)
            lambda_config = dedent("""\
                github_auth = (%r, %r)
                snooze_label = %r
                """) % (repo["github_username"],
                        repo["github_token"],
                        repo["snooze_label"])
            with open(os.path.join(tmpdir, "snooze", "lambda_config.py"), "w") as f:
                f.write(lambda_config)
            repo["zip_filename"] = "lambda_deploy-{}.zip".format(repository_name.replace("/", "_"))
            curdir = os.getcwd()
            os.chdir(tmpdir)
            zip_list = glob.glob("*")
            sp.check_call((["zip", "-r", os.path.join(curdir, repo["zip_filename"])] +
                           zip_list +
                           ["--exclude", "*.pyc"]),
                          stdout=devnull, stderr=sp.STDOUT)
            os.chdir(curdir)
    finally:
        shutil.rmtree(tmpdir)
        devnull.close()


def create_or_update_lambda_function(execution_role, function_name, repo):
    """Uploads Lambda deployment package to AWS.

    Args:
        execution_role (boto3.IAM.Role): IAM role to use as the execution
            context for the Lambda function.
        function_name (str): Name to use for the function in AWS
        repo (dict): Repository configuration object; one of the values of the
            configuration dictionary returned from parse_config. `repo` is
            expected to contain a "zip_filename" key, added by create_deployment_packages.

    Returns: function_arn (str)
    """
    with open(repo["zip_filename"], "rb") as f:
        package_zip = f.read()
    client = boto3.client("lambda", region_name=repo["aws_region"])
    function_arn = None
    for page in client.get_paginator("list_functions").paginate():
        for f in page["Functions"]:
            if f["FunctionName"] == function_name:
                function_arn = f["FunctionArn"]
                break

    if function_arn:
        client.update_function_code(
            FunctionName=function_name,
            ZipFile=package_zip)
    else:
        response = client.create_function(
            FunctionName=function_name,
            Runtime="python2.7",
            Role=execution_role.arn,
            Handler="lambda_handler.lambda_handler",
            Code={"ZipFile": package_zip},
            Timeout=10,
            MemorySize=128
        )
        function_arn = response["FunctionArn"]
    return function_arn


def main():
    if sys.version_info[:2] != (2, 7):
        logging.error("Must execute with Python 2.7")
        return False

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    config = snooze.parse_config(args.config)
    create_deployment_packages(config)
    iam_role = create_or_get_lambda_role()

    for repository_name, repo in config.items():
        logging.info("Configuring repository %s" % repository_name)
        # set up SNS topic and connect Github
        sns = boto3.resource("sns", region_name=repo["aws_region"])
        topic = sns.create_topic(Name=repository_name.replace("/", "__"))
        snooze.connect_github_to_sns(
            sns_topic_arn=topic.arn,
            events=snooze.constants.LISTEN_EVENTS,
            **repo)

        # upload a Lambda package
        function_name = "snooze__{}".format(repo["repository_name"].replace("/", "__"))
        function_arn = create_or_update_lambda_function(iam_role, function_name, repo)

        lambda_client = boto3.client("lambda", region_name=repo["aws_region"])
        try:
            # give the SNS topic permission to invoke the Lambda function
            lambda_client.add_permission(
                FunctionName=function_name,
                StatementId="1",
                Action="lambda:InvokeFunction",
                Principal="sns.amazonaws.com",
                SourceArn=topic.arn
            )
        except ClientError:
            logging.debug("Received ClientError; permission probably already exists")

        # connect the SNS topic to the Lambda function
        topic.subscribe(
            Protocol="lambda",
            Endpoint=function_arn
        )

        logging.info("Connected repository %s" % repository_name)


if __name__ == "__main__":
    sys.exit(main() is True)
