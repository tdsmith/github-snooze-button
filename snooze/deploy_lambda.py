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


def main():
    if sys.version_info[:2] != (2, 7):
        logging.error("Must execute with Python 2.7")
        return False

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    # parse config
    config = snooze.parse_config(args.config)

    # get the list of packages snooze requires
    dist = pkg_resources.get_distribution("github-snooze-button")
    requires = [str(i) for i in dist.requires()]

    # Amazon provides boto3
    requires = [i for i in requires if not i.starts_with("boto3")]

    # install requests somewhere
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
        with open(repo["zip_filename"], "rb") as f:
            package_zip = f.read()
        function_name = "snooze__{}".format(repository_name.replace("/", "__"))
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
                Role=iam_role.arn,
                Handler="lambda_handler.lambda_handler",
                Code={"ZipFile": package_zip},
                Timeout=10,
                MemorySize=128
            )
            function_arn = response["FunctionArn"]

        try:
            # give the SNS topic permission to invoke the Lambda function
            client.add_permission(
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
