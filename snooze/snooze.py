from __future__ import absolute_import

import argparse
import logging
import sys
import threading
import time

from snooze.callbacks import github_callback
from snooze.config import parse_config
from snooze.constants import LISTEN_EVENTS
from snooze.repository_listener import RepositoryListener

logging.basicConfig(level=logging.DEBUG)


def poll_forever(repo_listener, wait):
    while True:
        repo_listener.poll()
        logging.debug("Waiting {}s before polling {}".
                      format(wait, repo_listener.repository_name))
        time.sleep(wait)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    config = parse_config(args.config)
    for name, repo in config.items():
        github_auth = (repo["github_username"], repo["github_password"])
        snooze_label = repo["snooze_label"]
        callback = lambda event, message: github_callback(event, message, github_auth, snooze_label)
        listener = RepositoryListener(
            callbacks=[callback],
            events=LISTEN_EVENTS,
            **repo)
        t = threading.Thread(target=poll_forever, args=(listener, repo["poll_interval"]))
        t.daemon = True
        t.start()
    while True:
        # wait forever for a signal or an unusual termination
        if threading.active_count() < len(config) + 1:
            logging.error("Child polling thread quit!")
            return False
        time.sleep(1)
    return True

if __name__ == "__main__":
    sys.exit(not main())
