import json
from textwrap import dedent

import pytest
import responses
from testfixtures import LogCapture

import snooze
import github_responses


class TestGithubWebhookCallback(object):
    @pytest.fixture
    def config(self, tmpdir):
        config = tmpdir.join("config.txt")
        config.write(dedent("""\
            [baxterthehacker/public-repo]
            github_username: frodo
            github_token: baggins
            aws_key: shire
            aws_secret: precious
            aws_region: us-west-2
            snooze_label: snooze
            """))
        return snooze.parse_config(str(config))["baxterthehacker/public-repo"]

    @responses.activate
    def test_issue_comment_callback(self, config):
        """Test that a snooze label is removed from issues when a new comment
        is received."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/2")
        r = snooze.github_callback(
            "issue_comment",
            json.loads(github_responses.SNOOZED_ISSUE_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is True
        assert len(responses.calls) == 1

    @responses.activate
    def test_issue_comment_callback_not_snoozed(self, config):
        """Don't do anything on receiving an unsnoozed message."""
        r = snooze.github_callback(
            "issue_comment",
            json.loads(github_responses.UNSNOOZED_ISSUE_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is False
        assert len(responses.calls) == 0

    @responses.activate
    def test_pr_synchronize_callback(self, config):
        """Test that a snooze label is removed from PRs when a new commit is
        pushed."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/octocat/Hello-World/issues/1347")
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.SNOOZED_ISSUE_GET)
        r = snooze.github_callback(
            "pull_request",
            json.loads(github_responses.PULL_REQUEST),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is True
        assert len(responses.calls) == 2

    @responses.activate
    def test_pr_synchronize_callback_not_snoozed(self, config):
        """Test that a snooze label is not removed from PRs when a new commit is
        pushed but there is no snooze label."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.UNSNOOZED_ISSUE_GET)
        r = snooze.github_callback(
            "pull_request",
            json.loads(github_responses.PULL_REQUEST),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is False
        assert len(responses.calls) == 1

    @responses.activate
    def test_pr_commit_comment_callback(self, config):
        """Test that a snooze label is removed from PRs when a new commit is
        pushed."""
        responses.add(
            responses.PATCH,
            "https://api.github.com/repos/octocat/Hello-World/issues/1347")
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.SNOOZED_ISSUE_GET)
        r = snooze.github_callback(
            "pull_request_review_comment",
            json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is True
        assert len(responses.calls) == 2

    @responses.activate
    def test_pr_commit_comment_callback_not_snoozed(self, config):
        """Test that a snooze label is not removed from PRs when a new commit is
        pushed but there is no snooze label."""
        responses.add(
            responses.GET,
            "https://api.github.com/repos/baxterthehacker/public-repo/issues/1",
            body=github_responses.UNSNOOZED_ISSUE_GET)
        r = snooze.github_callback(
            "pull_request_review_comment",
            json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"])
        assert r is False
        assert len(responses.calls) == 1

    def test_bad_callback_type_is_logged(self, config):
        with LogCapture() as l:
            snooze.github_callback("foobar", None, None, None)
            assert "WARNING" in str(l)
