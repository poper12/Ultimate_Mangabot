
from os import path as ospath
from subprocess import run as srun

# Check if 'cache' file exists and truncate it if necessary
if ospath.exists("cache"):
    with open("cache", "r+") as f:
        f.truncate(0)

# Define the upstream repository and branch
UPSTREAM_REPO = (
    "https://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@github.com/voatxm/MangaUltimate"
)

UPSTREAM_BRANCH = "master"
USERNAME = "voatxm"
EMAIL = "Voatxm@gmail.com"

# Check if the UPSTREAM_REPO is defined
if UPSTREAM_REPO is not None:
    # If a .git directory exists, remove it
    if ospath.exists(".git"):
        srun(["rm", "-rf", ".git"])

    # Prepare and execute the git commands
    update = srun(
        [
            f"git init -q \
                     && git config --global user.email {EMAIL} \
                     && git config --global user.name {USERNAME} \
                     && git add . \
                     && git commit -sm 'update' -q \
                     && git remote add origin {UPSTREAM_REPO} \
                     && git fetch origin -q \
                     && git reset --hard origin/{UPSTREAM_BRANCH} -q"
        ],
        shell=True,
        capture_output=True,  # Capture both stdout and stderr
    )

    # Check if the update was successful
    if update.returncode == 0:
        print("Successfully updated with latest commit from UPSTREAM_REPO")
    else:
        print("Something went wrong while updating, check UPSTREAM_REPO if valid or not!")
        print(f"Error: {update.stderr.decode()}")
