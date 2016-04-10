import json
from textwrap import dedent

import pytest
import responses
import requests
from testfixtures import LogCapture

import snooze
import snooze.callbacks
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
            config["snooze_label"],
            config["ignore_members_of"])
        assert r is True
        assert len(responses.calls) == 1

        org_url = "https://api.github.com/orgs/fellowship/members/baxterthehacker"
        responses.add(responses.GET, org_url, status=204)  # is a member
        r = snooze.github_callback(
            "issue_comment",
            json.loads(github_responses.SNOOZED_ISSUE_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"],
            ignore_members_of="fellowship")
        assert r is False

        orc_url = "https://api.github.com/orgs/orcs/members/baxterthehacker"
        responses.add(responses.GET, orc_url, status=404)  # is not a member
        r = snooze.github_callback(
            "issue_comment",
            json.loads(github_responses.SNOOZED_ISSUE_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"],
            ignore_members_of="orcs")
        assert r is True

    @responses.activate
    def test_issue_comment_callback_not_snoozed(self, config):
        """Don't do anything on receiving an unsnoozed message."""
        r = snooze.github_callback(
            "issue_comment",
            json.loads(github_responses.UNSNOOZED_ISSUE_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"],
            config["ignore_members_of"])
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
            config["snooze_label"],
            config["ignore_members_of"])
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
            config["snooze_label"],
            config["ignore_members_of"])
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
            config["snooze_label"],
            config["ignore_members_of"])
        assert r is True
        assert len(responses.calls) == 2

        org_url = "https://api.github.com/orgs/fellowship/members/baxterthehacker"
        responses.add(responses.GET, org_url, status=204)  # is a member
        r = snooze.github_callback(
            "pull_request_review_comment",
            json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"],
            ignore_members_of="fellowship")
        assert r is False

        orc_url = "https://api.github.com/orgs/orcs/members/baxterthehacker"
        responses.add(responses.GET, orc_url, status=404)  # is not a member
        r = snooze.github_callback(
            "pull_request_review_comment",
            json.loads(github_responses.PULL_REQUEST_REVIEW_COMMENT),
            (config["github_username"], config["github_token"]),
            config["snooze_label"],
            ignore_members_of="orcs")
        assert r is True

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
            config["snooze_label"],
            config["ignore_members_of"])
        assert r is False
        assert len(responses.calls) == 1

    def test_bad_callback_type_is_logged(self, config):
        with LogCapture() as l:
            snooze.github_callback("foobar", None, None, None, None)
            assert "WARNING" in str(l)


class TestIsMember(object):
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
            ignore_members_of: fellowship
            """))
        return snooze.parse_config(str(config))["baxterthehacker/public-repo"]

    @pytest.fixture
    def github_auth(self, config):
        return (config["github_username"], config["github_token"])

    @responses.activate
    def test_is_member_true(self, config, github_auth):
        url = "https://api.github.com/orgs/fellowship/members/bilbo"
        responses.add(responses.GET, url, status=204)
        assert snooze.callbacks.is_member_of(github_auth, "bilbo", "fellowship")

    @responses.activate
    def test_is_member_false(self, config, github_auth):
        url = "https://api.github.com/orgs/fellowship/members/sauron"
        responses.add(responses.GET, url, status=404)
        assert snooze.callbacks.is_member_of(github_auth, "sauron", "fellowship") is False

    @responses.activate
    def test_is_member_raises(self, config, github_auth):
        url = "https://api.github.com/orgs/fellowship/members/bilbo"
        responses.add(responses.GET, url, status=200)
        with pytest.raises(requests.exceptions.HTTPError):
            snooze.callbacks.is_member_of(github_auth, "bilbo", "fellowship")
