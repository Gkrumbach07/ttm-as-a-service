import json
import requests
import pandas as pd
from github import Github
from github.PullRequest import PullRequest as GithubPullRequest
from typing import Dict, List, Optional

_NORMALIZE_VAL = {
    "Class_0": "0-3 hrs",
    "Class_1": "3-6 hrs",
    "Class_2": "6-15 hrs",
    "Class_3": "15-24 hrs",
    "Class_4": "1-1.5 days",
    "Class_5": "1.5-2.5 days",
    "Class_6": "2.5-4.5 days",
    "Class_7": "4.5-8 days",
    "Class_8": "8-19 days",
    "Class_9": ">19 days",
}


def assign_pull_request_size(lines_changes: int) -> str:
    """Assign size of PR is label is not provided."""
    if lines_changes > 1000:
        return "XXL"
    elif lines_changes >= 500 and lines_changes <= 999:
        return "XL"
    elif lines_changes >= 100 and lines_changes <= 499:
        return "L"
    elif lines_changes >= 30 and lines_changes <= 99:
        return "M"
    elif lines_changes >= 10 and lines_changes <= 29:
        return "S"
    elif lines_changes >= 0 and lines_changes <= 9:
        return "XS"
    else:
        return "NaN"


def get_interactions(comments) -> Dict:
    """Get overall word count for comments per author."""
    interactions = {comment.user.login: 0 for comment in comments}
    for comment in comments:
        # we count by the num of words in comment
        interactions[comment.user.login] += len(comment.body.split(" "))
    return interactions


def get_labeled_size(labels: List[str]) -> Optional[str]:
    """Extract size label from list of labels.
    Size label is in form 'size/<SIZE>', where <SIZE> can be
    XS, S, L, etc...
    """
    for label in labels:
        if label.startswith("size"):
            return label.split("/")[1]
    return None


def get_first_review_time(reviews) -> Optional[int]:
    """Return timestamp of the first PR review."""
    rev_times = [int(rev["submitted_at"]) for rev in reviews.values()]
    return min(rev_times) if rev_times else None


def get_approve_time(reviews) -> Optional[int]:
    """Return timestamp of the first PR approve review."""
    approvals = [
        rev["submitted_at"] for rev in reviews.values() if rev["state"] == "APPROVED"
    ]
    return min(approvals) if approvals else None


def extract_pull_request_reviews(
    pull_request: GithubPullRequest,
):
    """Extract required features for each review from PR.
    Arguments:
        pull_request {PullRequest} -- Pull Request from which the reviews will be extracted
    Returns:
        Dict[str, Dict[str, Any]] -- dictionary of extracted reviews. Each review is stored
    """
    reviews = pull_request.get_reviews()

    results = {}
    for idx, review in enumerate(reviews, 1):
        results[str(review.id)] = {
            "author": review.user.login if review.user and review.user.login else None,
            "words_count": len(review.body.split(" ")),
            "submitted_at": int(review.submitted_at.timestamp()),
            "state": review.state,
        }
    return results


def parse_pr_with_mi(pull_request: GithubPullRequest):
    """Extract parsed pull request into MI resultant pr json."""
    created_at = int(pull_request.created_at.timestamp())
    closed_at = (
        int(pull_request.closed_at.timestamp())
        if pull_request.closed_at is not None
        else None
    )
    merged_at = (
        int(pull_request.merged_at.timestamp())
        if pull_request.merged_at is not None
        else None
    )

    closed_by = (
        pull_request.as_issue().closed_by.login
        if pull_request.as_issue().closed_by is not None
        else None
    )
    merged_by = (
        pull_request.merged_by.login if pull_request.merged_by is not None else None
    )

    labels = [label.name for label in pull_request.get_labels()]

    # Evaluate size of PR
    pull_request_size = None
    if labels:
        pull_request_size = get_labeled_size(labels)

    if not pull_request_size:
        lines_changes = pull_request.additions + pull_request.deletions
        pull_request_size = assign_pull_request_size(lines_changes=lines_changes)

    reviews = extract_pull_request_reviews(pull_request)

    pr = {
        "title": pull_request.title,
        "body": pull_request.body,
        "size": pull_request_size,
        "created_by": pull_request.user.login,
        "created_at": created_at,
        "closed_at": closed_at,
        "closed_by": closed_by,
        "merged_at": merged_at,
        "merged_by": merged_by,
        "commits_number": pull_request.commits,
        "changed_files_number": pull_request.changed_files,
        "interactions": get_interactions(pull_request.get_issue_comments()),
        "reviews": reviews,
        "labels": labels,
        "commits": [c.sha for c in pull_request.get_commits()],
        "changed_files": [f.filename for f in pull_request.get_files()],
        "first_review_at": get_first_review_time(reviews),
        "first_approve_at": get_approve_time(reviews),
    }
    return pr


def get_mi_parsed_pr(repo_id, pr_id, gh_token):
    gh = Github(login_or_token=gh_token, timeout=50)
    repo = gh.get_repo(repo_id)
    prs = repo.get_pull(int(pr_id))
    pr = parse_pr_with_mi(prs)
    return pr


def get_ttm(model_url, repo_id, pr_id, gh_token):
    d = get_mi_parsed_pr(repo_id, pr_id, gh_token)
    pr_df = pd.DataFrame.from_dict(d, orient="index")
    pr_df = pr_df.transpose()
    data = {
        "data": {"names": pr_df.columns.tolist(), "ndarray": pr_df.to_numpy().tolist()}
    }
    headers = {"content-Type": "application/json"}
    r = requests.post(model_url, data=json.dumps(data), headers=headers)
    if not str(r.status_code).startswith("2"):
        print("Error: %d" % (r.status_code))
    else:
        res = r.json()
        values = res["data"].get("ndarray", [[]])[0]
        index_min = max(range(len(values)), key=values.__getitem__)
        if res["data"].get("names"):
            return _NORMALIZE_VAL.get(res["data"].get("names")[index_min])
    return "Unknown"
