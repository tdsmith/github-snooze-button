import logging
import requests

GITHUB_HEADERS = {"Accept": "application/vnd.github.v3+json"}
LISTEN_EVENTS = ["issue_comment",
                 "pull_request",
                 "pull_request_review_comment",
                 ]
SNOOZE_LABEL = "snooze"
logging.basicConfig(level=logging.DEBUG)


def github_patch(config, repo, url, data):
    repo_config = None
    for r in config:
        if r["repository_name"] == repo:
            repo_config = r
            break
    auth = requests.auth.HTTPBasicAuth(
        repo_config["github_username"],
        repo_config["github_token"])
    return requests.patch(url, auth=auth, json=data)


def github_callback(config, event, message):
    if event == "issue_comment":
        # When an issue is updated, we want to clear the SNOOZE_LABEL if it's set.
        issue = message["issue"]
        issue_labels = {label["name"] for label in issue.get("labels", [])}
        if SNOOZE_LABEL in issue_labels:
            issue_labels.remove(SNOOZE_LABEL)
            r = github_patch(
                config,
                message["repository"]["full_name"],
                issue["url"],
                {"labels": list(issue_labels)})
            r.raise_for_status()
    else:
        logging.debug("Ignoring event type {}" % event)


def main():
    # parse config
    # consume update
    pass
