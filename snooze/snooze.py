from __future__ import print_function

import argparse
import logging
import requests
import threading
import time

from .config import parse_config
from .constants import GITHUB_HEADERS
from .repository_listener import RepositoryListener

LISTEN_EVENTS = ["issue_comment",
                 "pull_request",
                 "pull_request_review_comment",
                 ]
SNOOZE_LABEL = "snooze"
logging.basicConfig(level=logging.DEBUG)


def github_patch(config, repo, url, data):
    repo_config = config[repo]
    auth = requests.auth.HTTPBasicAuth(
        repo_config["github_username"],
        repo_config["github_token"])
    return requests.patch(url, auth=auth, json=data, headers=GITHUB_HEADERS)


def github_get(config, repo, url):
    repo_config = config[repo]
    auth = requests.auth.HTTPBasicAuth(
        repo_config["github_username"],
        repo_config["github_token"])
    return requests.get(url, auth=auth, headers=GITHUB_HEADERS)


def clear_snooze_label_if_set(config, repo, issue):
    issue_labels = {label["name"] for label in issue.get("labels", [])}
    if SNOOZE_LABEL not in issue_labels:
        logging.debug(
            "clear_snooze_label_if_set: Label not set on {}".format(
                issue["html_url"]
            ))
        return False
    issue_labels.remove(SNOOZE_LABEL)
    r = github_patch(
        config,
        repo,
        issue["url"],
        {"labels": list(issue_labels)})
    r.raise_for_status()
    logging.debug(
        "clear_snooze_label_if_set: Removed snooze label from {}".format(
            issue["html_url"]
        ))
    return True


def github_callback(config, event, message):
    if event == "issue_comment":
        # When an issue is updated, we want to clear the SNOOZE_LABEL if it's set.
        issue = message["issue"]
        logging.debug("Incoming issue hook: {}".format(issue["html_url"]))
        return clear_snooze_label_if_set(
            config,
            message["repository"]["full_name"],
            issue)
    elif event == "pull_request":
        logging.debug("Incoming PR hook: {}".
                      format(message["pull_request"]["html_url"]))
        # We should take action when a pull request is synchronized.
        if message["action"] != "synchronize":
            return False
        logging.debug("Synchronize hook for PR: {}".
                      format(message["pull_request"]["html_url"]))
        # Fetch the matching issue object to see if SNOOZE_LABEL is set
        r = github_get(
            config,
            message["repository"]["full_name"],
            message["pull_request"]["issue_url"])
        r.raise_for_status()
        issue = r.json()
        return clear_snooze_label_if_set(
            config,
            message["repository"]["full_name"],
            issue)
    elif event == "pull_request_review_comment":
        logging.debug("Incoming PR comment hook: {}".
                      format(message["pull_request"]["html_url"]))
        # Fetch the matching issue object to see if SNOOZE_LABEL is set
        r = github_get(
            config,
            message["repository"]["full_name"],
            message["pull_request"]["issue_url"])
        r.raise_for_status()
        issue = r.json()
        return clear_snooze_label_if_set(
            config,
            message["repository"]["full_name"],
            issue)
    else:
        logging.warning("Ignoring event type {}".format(event))

    return False


def poll_forever(repo_listener, wait):
    while True:
        repo_listener.poll()
        time.sleep(wait)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    config = parse_config(args.config)
    for name, repo in config.items():
        callback = lambda event, message: github_callback(config, event, message)
        listener = RepositoryListener(
            callbacks=[callback],
            events=LISTEN_EVENTS,
            **repo)
        t = threading.Thread(target=poll_forever, args=(listener, 0))
        t.daemon = True
        t.start()
    while True:
        if threading.active_count() < len(config):
            logging.error("Child polling thread quit!")
            return False
        time.sleep(1)
    return True

if __name__ == "__main__":
    main()
