import os

from flask import Flask
from flask_githubapp import GitHubApp

import ttm_github_pr

app = Flask(__name__)

app.config["GITHUBAPP_ID"] = int(os.environ["GITHUBAPP_ID"])
app.config["GITHUBAPP_SECRET"] = os.environ["GITHUBAPP_SECRET"]
app.config["GITHUBAPP_KEY"] = os.environ["GITHUBAPP_KEY"]


github_app = GitHubApp(app)


@app.route("/")
def root():
    return "This is a webhook server"


@github_app.on("pull_request")
def process_pr_webhook():
    # TODO if model exists (training is done and model is published to seldon)
    # Use predefined location for model i.e. "/{ord/repo}/predict"
    model_url = "http://thoth-github-ttm-ds-ml-workflows-ws.apps.smaug.na.operate-first.cloud/predict"
    prediction = ttm_github_pr.get_ttm(
        model_url,
        github_app.payload["repository"]["id"],
        github_app.payload["number"],
        github_app.installation_token,
    )
    pr = github_app.installation_client.pull_request(
        github_app.payload["repository"]["owner"]["login"],
        github_app.payload["repository"]["name"],
        github_app.payload["number"],
    )

    pr.create_comment(prediction)


@github_app.on("installation.created")
def install_app():
    print("installed")


@github_app.on("installation.deleted")
def uninstall_app():
    print("removed")
