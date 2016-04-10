from __future__ import absolute_import

import logging

import requests

import snooze.constants as constants


def clear_snooze_label_if_set(github_auth, issue, snooze_label):
    issue_labels = {label["name"] for label in issue.get("labels", [])}
    if snooze_label not in issue_labels:
        logging.debug(
            "clear_snooze_label_if_set: Label {} not set on {}".
            format(snooze_label, issue["html_url"]))
        return False
    issue_labels.remove(snooze_label)
    auth = requests.auth.HTTPBasicAuth(*github_auth)
    r = requests.patch(issue["url"], auth=auth,
                       json={"labels": list(issue_labels)},
                       headers=constants.GITHUB_HEADERS)
    r.raise_for_status()
    logging.debug(
        "clear_snooze_label_if_set: Removed snooze label from {}".
        format(issue["html_url"]))
    return True


def fetch_pr_issue(github_auth, pull_request):
    auth = requests.auth.HTTPBasicAuth(*github_auth)
    r = requests.get(pull_request["issue_url"], auth=auth,
                     headers=constants.GITHUB_HEADERS)
    r.raise_for_status()
    return r.json()


def is_member_of(github_auth, user, organization):
    auth = requests.auth.HTTPBasicAuth(*github_auth)
    url = "https://api.github.com/orgs/{}/members/{}".format(organization, user)
    r = requests.get(url, auth=auth, headers=constants.GITHUB_HEADERS)
    if r.status_code == 204:
        return True
    elif r.status_code == 404:
        return False
    else:
        raise requests.exceptions.HTTPError(
            "Unexpected HTTP status %d" % r.status_code,
            response=r)


def github_callback(event, message, github_auth, snooze_label, ignore_members_of):
    if event == "issue_comment":
        issue = message["issue"]
        logging.debug("Incoming issue: {}".format(issue["html_url"]))
        author = message["comment"]["user"]["login"]
        if ignore_members_of and is_member_of(github_auth, author, ignore_members_of):
            return False
        return clear_snooze_label_if_set(github_auth, issue, snooze_label)

    elif event == "pull_request_review_comment":
        pull_request = message["pull_request"]
        logging.debug("Incoming PR comment hook: {}".format(pull_request["html_url"]))
        author = message["comment"]["user"]["login"]
        issue = fetch_pr_issue(github_auth, pull_request)
        if ignore_members_of and is_member_of(github_auth, author, ignore_members_of):
            return False
        return clear_snooze_label_if_set(github_auth, issue, snooze_label)

    elif event == "pull_request":
        pull_request = message["pull_request"]
        if message["action"] != "synchronize":
            return False
        logging.debug("Incoming PR hook: {} {}".
                      format(message["action"], pull_request["html_url"]))
        issue = fetch_pr_issue(github_auth, pull_request)
        return clear_snooze_label_if_set(github_auth, issue, snooze_label)

    else:
        logging.warning("Ignoring event type {}".format(event))
    return False
