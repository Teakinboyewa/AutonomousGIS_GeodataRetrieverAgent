# -*- coding: utf-8 -*-
"""
Share a user's handbook with everyone by contributing it to the plugin's
GitHub repository as a pull request.

With a GitHub personal access token, ``submit_handbook`` does the whole flow:
find the user's GitHub name -> fork the repository (or, for the repository
owner, use it directly) -> create a branch -> add
LLM_Find/Handbooks/<ID>.toml and a .keys template with EMPTY values ->
open a pull request. After the maintainer reviews and merges it, the data
source ships to all users as a built-in source.

API key values are never sent: the .keys template only names the
credentials, and the handbook is checked for stored key values and for
key-like strings before anything is uploaded.
"""
import base64
import configparser
import os
import re
import time
from urllib.parse import quote

import requests

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QThread, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.gui import QgsPasswordLineEdit

from . import llm_find_loader
from .debug_support import debug_this_thread

handbook_store = llm_find_loader.load('handbook')
hg = llm_find_loader.load('handbook_generator')

UPSTREAM_OWNER = "Teakinboyewa"
UPSTREAM_REPO = "AutonomousGIS_GeodataRetrieverAgent"
HANDBOOKS_PATH = "LLM_Find/Handbooks"
KEYS_PATH = "LLM_Find/Keys"
API = "https://api.github.com"
TOKEN_HELP_URL = ("https://github.com/settings/tokens/new?scopes=public_repo"
                  "&description=AutonomousGIS%20GeoData%20Retriever%20Agent")
_FORK_WAIT_SECONDS = 60

# Strings that look like secrets; a handbook containing one is not uploaded.
_SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9_\-]{20,}", "an OpenAI API key"),
    (r"gibd-services[A-Za-z0-9_\-]*", "a GIBD API key"),
    (r"gh[pousr]_[A-Za-z0-9]{30,}", "a GitHub token"),
    (r"github_pat_[A-Za-z0-9_]{30,}", "a GitHub token"),
    (r"AKIA[0-9A-Z]{16}", "an AWS access key"),
    (r"AIza[0-9A-Za-z_\-]{35}", "a Google API key"),
]


class GitHubError(Exception):
    """A GitHub problem explained in plain words for the user."""


# ── Token storage (in the user's QGIS profile, never in the plugin folder) ──

def _token_file():
    return os.path.join(handbook_store.User_data_dir, "github.ini")


def load_saved_token():
    config = configparser.ConfigParser(interpolation=None)
    config.read(_token_file(), encoding="utf-8")
    return config.get("GitHub", "token", fallback="")


def save_token(token):
    os.makedirs(handbook_store.User_data_dir, exist_ok=True)
    config = configparser.ConfigParser(interpolation=None)
    config["GitHub"] = {"token": token}
    with open(_token_file(), "w", encoding="utf-8") as fh:
        config.write(fh)


def forget_token():
    if os.path.exists(_token_file()):
        os.remove(_token_file())


# ── What is submitted ────────────────────────────────────────────────────

def find_secrets(text, source_id=None):
    """Reasons why ``text`` must not be published: stored key values (of any
    data source) appearing in it, or strings that look like secrets."""
    problems = []
    try:
        ids = handbook_store.list_handbook_ids()
    except Exception:
        ids = []
    for sid in ids:
        try:
            values = handbook_store.effective_keys(sid)
        except Exception:
            continue
        for name, value in values.items():
            if len(value) >= 6 and value in text:
                problems.append(f"the saved value of {name} ({sid})")
    for pattern, label in _SECRET_PATTERNS:
        if re.search(pattern, text):
            problems.append(f"something that looks like {label}")
    return sorted(set(problems))


def prepare_submission(source_id):
    """The files to add to the repository and a summary of the handbook.
    Raises GitHubError if the handbook cannot be shared."""
    path = os.path.join(handbook_store.User_handbooks_dir, f"{source_id}.toml")
    if not os.path.exists(path):
        raise GitHubError(f"'{source_id}' is not one of your saved handbooks. Save it first.")
    with open(path, encoding="utf-8") as fh:
        toml_text = fh.read()
    source = hg.load_toml_source(path)
    missing = [label for label, key in (("name", "data_source_name"), ("brief description", "brief_description"),
                                        ("handbook", "handbook")) if not source[key]]
    if missing:
        raise GitHubError("The handbook is missing its " + ", ".join(missing) + ". Complete it before sharing.")
    secrets = find_secrets(toml_text, source_id)
    if secrets:
        raise GitHubError("The handbook contains " + "; ".join(secrets) + ". Remove it (read keys with "
                          "os.environ[\"NAME\"] instead) and save the handbook again before sharing.")

    files = {f"{HANDBOOKS_PATH}/{source_id}.toml": toml_text}
    key_names = hg.split_key_names(source["key_name"]) if source["requires_key"] == "true" else []
    if key_names:
        lines = ["[API_Key]"] + [f"{name} = " for name in key_names]
        signup = source["key_signup_url"] or source["website"]
        if signup:
            lines += ["", "[Links]", f"website = {signup}"]
        files[f"{KEYS_PATH}/{source_id}.keys"] = "\n".join(lines) + "\n"
    return files, source


def _pull_request_body(source_id, source, note, tested, updates_existing):
    keys = hg.split_key_names(source["key_name"])
    lines = [
        f"## {'Updated' if updates_existing else 'New'} data source: {source['data_source_name']}",
        "",
        f"**Source ID:** `{source_id}`",
        "",
        f"**Description:** {source['brief_description']}",
        "",
        f"**Website:** {source['website'] or 'n/a'}",
        "",
        f"**Credentials:** {', '.join(f'`{k}`' for k in keys) + ' (values not included)' if keys else 'none needed'}",
        "",
        f"**Sample download test:** {tested or 'not run before sharing'}",
    ]
    if source.get("caveats"):
        lines += ["", f"**Caveats:** {source['caveats']}"]
    if note.strip():
        lines += ["", "### Note from the contributor", "", note.strip()]
    lines += ["", "---", "Submitted from the Handbook Studio of the AutonomousGIS GeoData Retriever Agent QGIS plugin."]
    return "\n".join(lines)


# ── GitHub REST API ─────────────────────────────────────────────────────

class GitHubClient:
    def __init__(self, token, session=None):
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {token.strip()}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": "AGGRA-QGIS-plugin"}

    def request(self, method, path, ok=(200, 201), **kwargs):
        try:
            resp = self.session.request(method, API + path, headers=self.headers, timeout=60, **kwargs)
        except requests.RequestException as e:
            raise GitHubError(f"Could not reach GitHub ({e}). Check your internet connection.")
        if resp.status_code in ok:
            return resp.json() if resp.content else {}
        try:
            message = resp.json().get("message", "")
        except ValueError:
            message = resp.text[:200]
        if resp.status_code == 401:
            raise GitHubError("GitHub did not accept the token. Check that it is correct and not expired.")
        if resp.status_code == 403 and "rate limit" in message.lower():
            raise GitHubError("GitHub's rate limit was reached. Try again in a few minutes.")
        if resp.status_code in (403, 404) and method != "GET":
            raise GitHubError(f"GitHub refused the request ({message}). The token needs the 'public_repo' "
                              "scope (classic token) or 'Contents' and 'Pull requests' write access "
                              "(fine-grained token).")
        raise GitHubError(f"GitHub error {resp.status_code}: {message}")

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def exists(self, path):
        """The resource's data, or None when GitHub answers 404."""
        try:
            return self.get(path)
        except GitHubError as e:
            if "404" in str(e):
                return None
            raise


def _contents_path(repo, path):
    return f"/repos/{repo}/contents/" + "/".join(quote(part) for part in path.split("/"))


def submit_handbook(token, source_id, note="", tested="", log=print, session=None, sleep=time.sleep):
    """Open a pull request that adds (or updates) ``source_id`` in the
    plugin repository. Returns the pull request URL."""
    files, source = prepare_submission(source_id)
    gh = GitHubClient(token, session)
    upstream = f"{UPSTREAM_OWNER}/{UPSTREAM_REPO}"

    log("Checking your GitHub account...")
    login = gh.get("/user")["login"]
    repo_info = gh.get(f"/repos/{upstream}")
    base = repo_info.get("default_branch") or "master"
    base_sha = gh.get(f"/repos/{upstream}/git/ref/heads/{quote(base)}")["object"]["sha"]
    updates_existing = gh.exists(
        _contents_path(upstream, f"{HANDBOOKS_PATH}/{source_id}.toml") + f"?ref={base}") is not None

    if login.lower() == UPSTREAM_OWNER.lower():
        head_repo = upstream
        log("You own the repository: the pull request is made from a branch in it.")
    else:
        log(f"Preparing your copy (fork) of the repository as {login}...")
        fork = gh.request("POST", f"/repos/{upstream}/forks", ok=(200, 202), json={"default_branch_only": True})
        head_repo = fork.get("full_name") or f"{login}/{UPSTREAM_REPO}"
        waited = 0
        while gh.exists(f"/repos/{head_repo}") is None:
            if waited >= _FORK_WAIT_SECONDS:
                raise GitHubError("GitHub is still creating your fork. Try again in a minute.")
            sleep(3)
            waited += 3

    branch = f"handbook/{source_id}-{time.strftime('%Y%m%d-%H%M%S')}"
    log(f"Creating branch {branch}...")
    try:
        gh.request("POST", f"/repos/{head_repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
    except GitHubError:
        # An older fork may not know the latest commit yet: bring it up to date and retry.
        gh.request("POST", f"/repos/{head_repo}/merge-upstream", ok=(200, 409), json={"branch": base})
        sha = gh.get(f"/repos/{head_repo}/git/ref/heads/{quote(base)}")["object"]["sha"]
        gh.request("POST", f"/repos/{head_repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})

    verb = "Update" if updates_existing else "Add"
    for path, text in files.items():
        log(f"Uploading {path}...")
        existing = gh.exists(_contents_path(head_repo, path) + f"?ref={quote(branch)}")
        body = {"message": f"{verb} data source handbook: {source['data_source_name']} ({os.path.basename(path)})",
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                "branch": branch}
        if existing and existing.get("sha"):
            body["sha"] = existing["sha"]
        gh.request("PUT", _contents_path(head_repo, path), json=body)

    log("Opening the pull request...")
    head = branch if head_repo == upstream else f"{head_repo.split('/')[0]}:{branch}"
    pr = gh.request("POST", f"/repos/{upstream}/pulls", json={
        "title": f"{verb} data source: {source['data_source_name']}",
        "head": head, "base": base,
        "body": _pull_request_body(source_id, source, note, tested, updates_existing),
        "maintainer_can_modify": True,
    })
    log(f"Pull request opened: {pr['html_url']}")
    return pr["html_url"]


# ── Dialog ──────────────────────────────────────────────────────────────

class _SubmitWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, token, source_id, note, tested, parent=None):
        super().__init__(parent)
        self._args = (token, source_id, note, tested)

    def run(self):
        debug_this_thread()
        try:
            token, source_id, note, tested = self._args
            self.done.emit(submit_handbook(token, source_id, note, tested, log=self.log.emit))
        except GitHubError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class ShareOnGitHubDialog(QtWidgets.QDialog):
    """Submit one of the user's handbooks to the plugin repository."""

    def __init__(self, source_id, tested="", parent=None):
        super().__init__(parent)
        self.source_id = source_id
        self.tested = tested
        self._worker = None
        self.pr_url = ""
        self.setWindowTitle("Share on GitHub")
        self.setMinimumSize(620, 620)

        try:
            files, source = prepare_submission(source_id)
            problem = ""
        except GitHubError as e:
            files, source, problem = {}, None, str(e)

        intro = QtWidgets.QLabel(
            "<b>Share this data source with everyone.</b><br>It is sent to the plugin's GitHub repository as a "
            "<i>pull request</i>. After the maintainers review and accept it, it becomes a built-in data "
            "source for all users.")
        intro.setWordWrap(True)

        summary = QtWidgets.QTextBrowser()  # sizes predictably and scrolls, unlike a wrapped QLabel
        summary.setFixedHeight(150)
        summary.setOpenExternalLinks(True)
        if source:
            keys = hg.split_key_names(source["key_name"])
            summary.setText(
                f"<b>{_esc(source['data_source_name'])}</b> (<code>{_esc(source_id)}</code>)<br>"
                f"Files added to the repository:<br>"
                + "".join(f"&nbsp;&nbsp;&bull; <code>{_esc(p)}</code><br>" for p in files)
                + (f"Credentials: {_esc(', '.join(keys))} - <b>values are not included</b><br>" if keys else "")
                + f"Sample download test: {_esc(tested or 'not run - consider testing it first')}")
        else:
            summary.setText(f"<span style='color:#a31b1b'>{_esc(problem)}</span>")
        summary.setStyleSheet("QTextBrowser { background: #f4f6f8; border: 1px solid #e3e8ec; border-radius: 6px; "
                              "padding: 4px; }")

        self.token_edit = QgsPasswordLineEdit()
        self.token_edit.setPlaceholderText("ghp_... or github_pat_...")
        self.token_edit.setText(load_saved_token())
        token_help = QtWidgets.QLabel(
            f"A GitHub personal access token lets the plugin open the pull request for you. "
            f"<a href='{TOKEN_HELP_URL}'>Create a token</a> (classic, with the <code>public_repo</code> scope). "
            "You need a free GitHub account.")
        token_help.setWordWrap(True)
        token_help.setOpenExternalLinks(True)
        token_help.setStyleSheet("color: #74838c;")
        self.remember_check = QtWidgets.QCheckBox("Remember the token on this computer")
        self.remember_check.setChecked(bool(self.token_edit.text()))

        self.note_edit = QtWidgets.QPlainTextEdit()
        self.note_edit.setPlaceholderText("Optional: anything the reviewers should know (what you tested, "
                                          "limitations, your affiliation...)")
        self.note_edit.setFixedHeight(80)

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setVisible(False)

        self.result_label = QtWidgets.QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setOpenExternalLinks(True)
        self.result_label.setVisible(False)

        self.submit_btn = QtWidgets.QPushButton("Open pull request")
        self.submit_btn.setDefault(True)
        self.submit_btn.setEnabled(source is not None)
        self.submit_btn.setStyleSheet("QPushButton { background: #2c5f7c; color: white; border-radius: 6px; "
                                      "padding: 6px 14px; font-weight: 600; } "
                                      "QPushButton:disabled { background: #a7bccb; }")
        self.submit_btn.clicked.connect(self._submit)
        self.open_btn = QtWidgets.QPushButton("View on GitHub")
        self.open_btn.setVisible(False)
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.pr_url)))
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.submit_btn)
        buttons.addWidget(close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(intro)
        layout.addWidget(summary)
        layout.addWidget(QtWidgets.QLabel("<b>GitHub token</b>"))
        layout.addWidget(self.token_edit)
        layout.addWidget(token_help)
        layout.addWidget(self.remember_check)
        layout.addWidget(QtWidgets.QLabel("<b>Message to the reviewers</b>"))
        layout.addWidget(self.note_edit)
        layout.addWidget(self.result_label)
        layout.addWidget(self.log_view, 1)
        layout.addStretch(1)
        layout.addLayout(buttons)

    def _submit(self):
        token = self.token_edit.text().strip()
        if not token:
            QtWidgets.QMessageBox.information(self, "GitHub token needed",
                                              "Enter a GitHub personal access token first.")
            return
        if self.remember_check.isChecked():
            save_token(token)
        else:
            forget_token()
        self.submit_btn.setEnabled(False)
        self.log_view.clear()
        self.log_view.setVisible(True)
        self.result_label.setVisible(False)
        self._worker = _SubmitWorker(token, self.source_id, self.note_edit.toPlainText(), self.tested, self)
        self._worker.log.connect(self.log_view.appendPlainText)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, url):
        self.pr_url = url
        self.result_label.setText(
            f"<span style='color:#1a7f37'><b>Thank you! Your pull request is open:</b></span> "
            f"<a href='{url}'>{_esc(url)}</a><br>The maintainers will review it; you can follow the discussion "
            "on GitHub.")
        self.result_label.setVisible(True)
        self.open_btn.setVisible(True)
        self.open_btn.setDefault(True)
        self.submit_btn.setVisible(False)  # already shared; avoid a duplicate pull request

    def _on_failed(self, message):
        self.result_label.setText(f"<span style='color:#a31b1b'><b>Not shared:</b> {_esc(message)}</span>")
        self.result_label.setVisible(True)
        self.submit_btn.setEnabled(True)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(5000)
        super().closeEvent(event)


def _esc(text):
    import html
    return html.escape(str(text or ""))
