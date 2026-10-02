# -*- coding: utf-8 -*-
"""
Handbook Studio: create a data-source handbook with AI or by hand.

One editable form is shared by both modes:
  * Generate with AI  - describe the source; the AI researches it, drafts the
                         handbook and (optionally) tests its code example.
  * Write manually    - start from a blank handbook, or open/import an
                         existing one and edit it.
The draft can be revised by chatting with the AI, tested, and saved to the
user handbook folder (outside the plugin, so it survives plugin updates).
"""
import os
import re
import sys

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QRegExp
from qgis.PyQt.QtGui import QFont, QRegExpValidator
from qgis.gui import QgsPasswordLineEdit

_LLM_FIND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'LLM_Find')
if _LLM_FIND_DIR not in sys.path:
    sys.path.append(_LLM_FIND_DIR)

import handbook as handbook_store  # noqa: E402
import handbook_generator as hg  # noqa: E402


_BLANK_CODE = '''import requests

def download_data():
    # Download a SMALL sample and save it to a file, e.g.:
    # resp = requests.get("https://example.org/api/data", params={...}, timeout=60)
    # resp.raise_for_status()
    # with open("sample.json", "w", encoding="utf-8") as f:
    #     f.write(resp.text)
    pass

download_data()
'''


class _Worker(QThread):
    """Runs ``fn(log, should_stop)`` off the GUI thread."""
    log = pyqtSignal(str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._stop = False

    def stop(self):
        self._stop = True

    def should_stop(self):
        return self._stop

    def run(self):
        try:
            self.done.emit(self._fn(self.log.emit, self.should_stop))
        except hg.Cancelled:
            self.failed.emit("Stopped.")
        except Exception as e:  # shown to the user, never crashes QGIS
            self.failed.emit(f"{type(e).__name__}: {e}")


class HandbookStudioDialog(QtWidgets.QDialog):
    """``settings_provider()`` returns {'api_key', 'model', 'reasoning_effort'}
    from the plugin's Settings tab at the moment they are needed."""
    handbook_saved = pyqtSignal(str)

    def __init__(self, settings_provider, python_exe, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Handbook Studio - Add a New Data Source")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.resize(1150, 800)
        self._settings_provider = settings_provider
        self._python_exe = python_exe
        self._worker = None
        self._chat_history = []
        self._loaded_user_id = ""    # user handbook currently being edited
        self._build_ui()
        self._refresh_existing()
        self._update_key_widgets()

    # ── UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_form_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom = QtWidgets.QHBoxLayout()
        self.folder_label = QtWidgets.QLabel(
            f"Your handbooks are saved in: <a href='file:///{handbook_store.User_handbooks_dir}'>"
            f"{handbook_store.User_handbooks_dir}</a>")
        self.folder_label.setOpenExternalLinks(True)
        self.folder_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        bottom.addWidget(self.folder_label, 1)
        bottom.addWidget(close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(bottom)

    def _build_left_panel(self):
        panel = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)

        self.mode_tabs = QtWidgets.QTabWidget()
        self.mode_tabs.addTab(self._build_ai_tab(), "Generate with AI")
        self.mode_tabs.addTab(self._build_manual_tab(), "Write manually")
        v.addWidget(self.mode_tabs)

        refine_box = QtWidgets.QGroupBox("Ask the AI to revise the draft")
        rv = QtWidgets.QVBoxLayout(refine_box)
        self.chat_view = QtWidgets.QPlainTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setPlaceholderText(
            "e.g. 'Save the output as GeoJSON instead of CSV', or paste an error message you got.")
        rv.addWidget(self.chat_view, 1)
        row = QtWidgets.QHBoxLayout()
        self.refine_input = QtWidgets.QLineEdit()
        self.refine_input.setPlaceholderText("What should change?")
        self.refine_input.returnPressed.connect(self._on_refine)
        self.refine_btn = QtWidgets.QPushButton("Send")
        self.refine_btn.clicked.connect(self._on_refine)
        row.addWidget(self.refine_input, 1)
        row.addWidget(self.refine_btn)
        rv.addLayout(row)
        v.addWidget(refine_box, 1)

        log_box = QtWidgets.QGroupBox("Progress")
        lv = QtWidgets.QVBoxLayout(log_box)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        lv.addWidget(self.log_view)
        v.addWidget(log_box, 1)
        return panel

    def _build_ai_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        intro = QtWidgets.QLabel(
            "Describe the data source or the data you need, or paste an API/documentation link. "
            "The AI finds the official source, reads its documentation, writes the handbook and a "
            "code example, and can test the code with a small sample download.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.backend_label = QtWidgets.QLabel()
        self.backend_label.setWordWrap(True)
        self.backend_label.setStyleSheet("color: #6f6f53; font-style: italic;")
        v.addWidget(self.backend_label)

        self.request_edit = QtWidgets.QPlainTextEdit()
        self.request_edit.setPlaceholderText(
            "e.g. 'NASA FIRMS active fire detections', 'USGS water data for streamflow', or "
            "'https://api.openaq.org'")
        self.request_edit.setMaximumHeight(90)
        v.addWidget(self.request_edit)

        self.website_edit = QtWidgets.QLineEdit()
        self.website_edit.setPlaceholderText("Website or documentation URL(s) (optional)")
        v.addWidget(self.website_edit)

        self.verify_check = QtWidgets.QCheckBox(
            "Test the code example with a small sample download, and let the AI fix failures")
        self.verify_check.setChecked(True)
        v.addWidget(self.verify_check)

        row = QtWidgets.QHBoxLayout()
        self.generate_btn = QtWidgets.QPushButton("Generate handbook")
        self.generate_btn.clicked.connect(self._on_generate)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        row.addWidget(self.generate_btn)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        return w

    def _build_manual_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        intro = QtWidgets.QLabel(
            "Write the handbook yourself in the form on the right. Start from a blank handbook, or open "
            "an existing one to adapt it. Editing a built-in handbook saves your own copy, which then "
            "replaces the built-in one for you.")
        intro.setWordWrap(True)
        v.addWidget(intro)

        blank_btn = QtWidgets.QPushButton("Start a blank handbook")
        blank_btn.clicked.connect(self._on_blank)
        v.addWidget(blank_btn)

        row = QtWidgets.QHBoxLayout()
        self.existing_combo = QtWidgets.QComboBox()
        open_btn = QtWidgets.QPushButton("Open")
        open_btn.clicked.connect(self._on_open_existing)
        self.delete_btn = QtWidgets.QPushButton("Delete")
        self.delete_btn.setToolTip("Delete one of your own handbooks")
        self.delete_btn.clicked.connect(self._on_delete)
        self.existing_combo.currentIndexChanged.connect(self._update_delete_button)
        row.addWidget(self.existing_combo, 1)
        row.addWidget(open_btn)
        row.addWidget(self.delete_btn)
        v.addLayout(row)

        import_btn = QtWidgets.QPushButton("Import a .toml file...")
        import_btn.clicked.connect(self._on_import)
        v.addWidget(import_btn)

        tips = QtWidgets.QLabel(
            "<b>Tips</b><ul>"
            "<li><b>Handbook</b>: one requirement per line (endpoint, parameters, formats, pitfalls).</li>"
            "<li>Keep the line with <code>{code_example}</code> so the AI sees your example code.</li>"
            "<li>If the source needs a key, enter its name(s) under <b>Key names</b> (the provider's own name, "
            "e.g. FIRMS_MAP_KEY). The code reads it with <code>os.environ[\"FIRMS_MAP_KEY\"]</code>; the "
            "handbook can write <code>{FIRMS_MAP_KEY}</code> where the value belongs.</li>"
            "<li>The code example should save a small sample to a file, so <b>Test code</b> can check it.</li>"
            "</ul>")
        tips.setWordWrap(True)
        tips.setTextFormat(Qt.RichText)
        v.addWidget(tips)
        v.addStretch(1)
        return w

    def _build_form_panel(self):
        mono = QFont("Consolas" if sys.platform == "win32" else "Monospace")
        mono.setStyleHint(QFont.Monospace)

        form_widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(form_widget)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        self.id_edit = QtWidgets.QLineEdit()
        self.id_edit.setValidator(QRegExpValidator(QRegExp(r"[A-Za-z0-9_]{0,60}")))
        self.id_edit.setPlaceholderText("e.g. NASA_FIRMS (letters, digits, underscores)")
        self.id_edit.textChanged.connect(self._update_key_widgets)
        form.addRow("Source ID:", self.id_edit)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Human-readable name, e.g. NASA FIRMS Active Fires")
        self.name_edit.editingFinished.connect(self._suggest_id)
        form.addRow("Data source name:", self.name_edit)

        self.desc_edit = QtWidgets.QPlainTextEdit()
        self.desc_edit.setPlaceholderText(
            "1-3 sentences telling the AI when to use this source: what data, extent and period.")
        self.desc_edit.setMaximumHeight(80)
        form.addRow("Brief description:", self.desc_edit)

        self.handbook_edit = QtWidgets.QPlainTextEdit()
        self.handbook_edit.setPlaceholderText("Technical requirements, one per line.")
        self.handbook_edit.setMinimumHeight(200)
        form.addRow("Handbook:", self.handbook_edit)

        self.code_edit = QtWidgets.QPlainTextEdit()
        self.code_edit.setFont(mono)
        self.code_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.code_edit.setMinimumHeight(200)
        form.addRow("Code example:", self.code_edit)

        self.website_field = QtWidgets.QLineEdit()
        form.addRow("Website:", self.website_field)

        self.requires_key_check = QtWidgets.QCheckBox("This data source needs an API key")
        self.requires_key_check.toggled.connect(self._update_key_widgets)
        form.addRow("", self.requires_key_check)

        self.key_name_edit = QtWidgets.QLineEdit()
        self.key_name_edit.setValidator(QRegExpValidator(QRegExp(r"[A-Za-z0-9_, ]*")))
        self.key_name_edit.setPlaceholderText("e.g. FIRMS_MAP_KEY  (comma-separated if several)")
        self.key_name_edit.textChanged.connect(self._rebuild_key_inputs)
        form.addRow("Key names:", self.key_name_edit)

        # One password field per credential name, rebuilt when the names change.
        self._key_inputs = {}
        self._key_values_cache = {}
        self.key_values_widget = QtWidgets.QWidget()
        self.key_values_form = QtWidgets.QFormLayout(self.key_values_widget)
        self.key_values_form.setContentsMargins(0, 0, 0, 0)
        form.addRow("", self.key_values_widget)

        self.placeholder_label = QtWidgets.QLabel()
        self.placeholder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.placeholder_label.setWordWrap(True)
        self.placeholder_label.setStyleSheet("color: #6f6f53;")
        form.addRow("", self.placeholder_label)

        self.signup_edit = QtWidgets.QLineEdit()
        self.signup_edit.setPlaceholderText("Where users register for a key (optional)")
        form.addRow("Key sign-up page:", self.signup_edit)

        self.caveats_edit = QtWidgets.QPlainTextEdit()
        self.caveats_edit.setPlaceholderText("Optional warnings: rate limits, paid tiers, coverage gaps...")
        self.caveats_edit.setMaximumHeight(60)
        form.addRow("Caveats:", self.caveats_edit)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.test_btn = QtWidgets.QPushButton("Test code")
        self.test_btn.setToolTip("Run the code example once in a separate Python process")
        self.test_btn.clicked.connect(self._on_test)
        self.save_btn = QtWidgets.QPushButton("Save handbook")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.status_label, 1)
        buttons.addWidget(self.test_btn)
        buttons.addWidget(self.save_btn)

        panel = QtWidgets.QGroupBox("Handbook")
        v = QtWidgets.QVBoxLayout(panel)
        v.addWidget(scroll, 1)
        v.addLayout(buttons)
        return panel

    # ── Form <-> dict ────────────────────────────────────────────────────
    def _current_source(self):
        return {
            "data_source_name": self.name_edit.text().strip(),
            "brief_description": self.desc_edit.toPlainText().strip(),
            "handbook": self.handbook_edit.toPlainText().strip(),
            "code_example": self.code_edit.toPlainText().rstrip() + "\n",
            "website": self.website_field.text().strip(),
            "requires_key": "true" if self.requires_key_check.isChecked() else "false",
            "key_name": ",".join(self._key_names()) if self.requires_key_check.isChecked() else "",
            "key_signup_url": self.signup_edit.text().strip(),
            "caveats": self.caveats_edit.toPlainText().strip(),
        }

    def _fill_form(self, source, source_id=None, key_values=None):
        if source_id is not None:
            self.id_edit.setText(source_id)
        if key_values is not None:
            self._key_values_cache = {k: v for k, v in key_values.items() if v}
            for name, edit in self._key_inputs.items():
                edit.setText(self._key_values_cache.get(name, ""))
        self.name_edit.setText(source.get("data_source_name", ""))
        self.desc_edit.setPlainText(source.get("brief_description", ""))
        self.handbook_edit.setPlainText(source.get("handbook", ""))
        self.code_edit.setPlainText(source.get("code_example", ""))
        self.website_field.setText(source.get("website", ""))
        self.requires_key_check.setChecked(source.get("requires_key") == "true")
        self.key_name_edit.setText(source.get("key_name", "").replace(",", ", "))
        self.signup_edit.setText(source.get("key_signup_url", ""))
        self.caveats_edit.setPlainText(source.get("caveats", ""))
        self._update_key_widgets()

    def _key_names(self):
        return list(dict.fromkeys(hg.split_key_names(self.key_name_edit.text())))

    def _key_values(self):
        """{credential name: value typed in the form} (only non-empty values)."""
        self._sync_key_cache()
        return {n: self._key_values_cache[n] for n in self._key_names() if self._key_values_cache.get(n)}

    def _sync_key_cache(self):
        for name, edit in self._key_inputs.items():
            self._key_values_cache[name] = edit.text().strip()

    def _rebuild_key_inputs(self):
        self._sync_key_cache()
        while self.key_values_form.rowCount():
            self.key_values_form.removeRow(0)
        self._key_inputs = {}
        for name in self._key_names():
            edit = QgsPasswordLineEdit()
            edit.setPlaceholderText("Your value (stored locally in the .keys file, never in the handbook)")
            edit.setText(self._key_values_cache.get(name, ""))
            edit.setEnabled(self.requires_key_check.isChecked())
            self._key_inputs[name] = edit
            self.key_values_form.addRow(f"{name}:", edit)
        self._update_placeholder_help()

    def _source_id(self):
        return self.id_edit.text().strip()

    def _suggest_id(self):
        if not self._source_id() and self.name_edit.text().strip():
            self.id_edit.setText(hg.make_source_id(self.name_edit.text()))

    def _update_key_widgets(self):
        needs_key = self.requires_key_check.isChecked()
        self.key_name_edit.setEnabled(needs_key)
        self.signup_edit.setEnabled(needs_key)
        for edit in self._key_inputs.values():
            edit.setEnabled(needs_key)
        self._update_placeholder_help()
        self._update_backend_label()

    def _update_placeholder_help(self):
        names = self._key_names()
        if not self.requires_key_check.isChecked():
            self.placeholder_label.setText("")
        elif not names:
            self.placeholder_label.setText(
                "Enter the credential name(s) the provider uses, e.g. FIRMS_MAP_KEY. "
                "One name per credential, not alternative spellings of the same one.")
        else:
            name = names[0]
            self.placeholder_label.setText(
                f"In the code example read it with <b>os.environ[\"{name}\"]</b>; in the handbook text "
                f"write <b>{{{name}}}</b> where the value belongs (e.g. in a header or URL). "
                "Values are supplied when data is requested.")

    def _update_backend_label(self):
        key = (self._settings().get("api_key") or "").strip()
        if not key:
            text = "No OpenAI or GIBD API key is set in the Settings tab - AI features are unavailable."
        elif "gibd-services" in key:
            text = ("Using your GIBD key: the AI cannot search the web, so it relies on its own knowledge "
                    "and on documentation URLs you give it. Adding the documentation URL helps a lot.")
        else:
            text = "Using your OpenAI key: the AI will search the web for the official documentation."
        self.backend_label.setText(text)

    def _settings(self):
        try:
            return self._settings_provider() or {}
        except Exception:
            return {}

    def _make_backend(self):
        """Build the AI backend on the GUI thread (it reads the Settings tab).
        Returns None, after telling the user, when no usable key is set."""
        s = self._settings()
        try:
            return hg.LLMBackend(s.get("api_key"), model=s.get("model"),
                                 reasoning_effort=s.get("reasoning_effort"))
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "API key needed", str(e))
            return None

    # ── Logging / busy state ─────────────────────────────────────────────
    def _log(self, text):
        self.log_view.appendPlainText(text)

    def _set_busy(self, busy):
        for w in (self.generate_btn, self.refine_btn, self.test_btn, self.save_btn, self.refine_input):
            w.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        if busy:
            self.status_label.setText("Working...")
        elif self.status_label.text() == "Working...":
            self.status_label.setText("")

    def _start(self, fn, on_done):
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = _Worker(fn, self)
        self._worker.log.connect(self._log)
        self._worker.done.connect(on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._set_busy(True)
        self._worker.start()

    def _on_failed(self, message):
        self._log(f"Error: {message}" if message != "Stopped." else "Stopped.")
        self.status_label.setText(message if len(message) < 200 else message[:200] + "...")

    def _on_stop(self):
        if self._worker is not None:
            self._worker.stop()
            self._log("Stopping after the current step...")

    # ── AI generation ────────────────────────────────────────────────────
    def _on_generate(self):
        query = self.request_edit.toPlainText().strip()
        if not query:
            QtWidgets.QMessageBox.information(self, "Describe the data source",
                                              "Describe the data source or paste its API link first.")
            return
        if self._has_unsaved_draft() and QtWidgets.QMessageBox.question(
                self, "Replace the current draft?",
                "Generating a new handbook replaces the draft in the form. Continue?") != QtWidgets.QMessageBox.Yes:
            return
        backend = self._make_backend()
        if backend is None:
            return
        website = self.website_edit.text().strip()
        verify = self.verify_check.isChecked()
        python_exe = self._python_exe
        keys = self._key_values()
        self.log_view.clear()
        self._chat_history = []
        self.chat_view.clear()

        def job(log, should_stop):
            return hg.generate_handbook(query, backend, website=website, verify=verify,
                                        python_exe=python_exe, keys=keys,
                                        log=log, should_stop=should_stop)
        self._start(job, self._on_generated)

    def _on_generated(self, result):
        source_id, source, report = result
        self._loaded_user_id = ""
        self._fill_form(source, source_id=source_id)
        self._show_report(report)

    def _show_report(self, report):
        if not report:
            return
        status = report.get("status")
        if status == "verified":
            self.status_label.setText("<span style='color:#2e7d32'>Tested: the sample download worked.</span>")
        elif status == "skipped_needs_key":
            missing = ", ".join(report.get("missing") or []) or "the API key"
            self.status_label.setText(f"Not tested yet: enter a value for {missing}, then press 'Test code'.")
        else:
            self.status_label.setText("<span style='color:#c62828'>The code example failed. "
                                      "See Progress, or ask the AI to fix it.</span>")
            err = (report.get("error") or "").strip()
            if err:
                self._log("Last error:\n" + err[-1500:])
                tail = "\n".join(err.splitlines()[-6:])
                self.refine_input.setText(f"The code example failed with this error, please fix it: {tail}")

    # ── Refinement ───────────────────────────────────────────────────────
    def _on_refine(self):
        message = self.refine_input.text().strip()
        if not message or (self._worker is not None and self._worker.isRunning()):
            return
        current = self._current_source()
        if not any(current[k].strip() for k in ("data_source_name", "handbook", "code_example")):
            QtWidgets.QMessageBox.information(self, "Nothing to revise",
                                              "Generate or write a handbook first.")
            return
        backend = self._make_backend()
        if backend is None:
            return
        source_id = self._source_id() or hg.make_source_id(current["data_source_name"])
        history = list(self._chat_history)
        self.chat_view.appendPlainText(f"You: {message}\n")
        self._chat_history.append({"role": "user", "content": message})
        self.refine_input.clear()

        def job(log, should_stop):
            log("Asking the AI to revise the handbook...")
            return hg.refine_handbook(current, message, backend, source_id, history=history, log=log)

        def done(result):
            source, reply = result
            self._fill_form(source, source_id=source_id)
            self.chat_view.appendPlainText(f"AI: {reply}\n")
            self._chat_history.append({"role": "assistant", "content": reply})
            self._log("Handbook revised. Press 'Test code' to check it.")
        self._start(job, done)

    # ── Testing ──────────────────────────────────────────────────────────
    def _on_test(self):
        source = self._current_source()
        source_id = self._source_id()
        if not source["code_example"].strip():
            QtWidgets.QMessageBox.information(self, "No code", "There is no code example to test.")
            return
        python_exe = self._python_exe
        keys = self._key_values()

        def job(log, should_stop):
            return hg.verify_source(source, source_id, python_exe, backend=None,
                                    keys=keys, log=log, should_stop=should_stop)
        self._start(job, lambda result: self._show_report(result[1]))

    # ── Manual mode ──────────────────────────────────────────────────────
    def _has_unsaved_draft(self):
        return bool(self.handbook_edit.toPlainText().strip() or self.name_edit.text().strip())

    def _on_blank(self):
        if self._has_unsaved_draft() and QtWidgets.QMessageBox.question(
                self, "Start over?", "Clear the current draft?") != QtWidgets.QMessageBox.Yes:
            return
        self._loaded_user_id = ""
        self._fill_form({"handbook": "Write your first requirement here.\n" + hg.HANDBOOK_TAIL,
                         "code_example": _BLANK_CODE, "requires_key": "false"}, source_id="", key_values={})
        self.name_edit.setFocus()

    def _refresh_existing(self):
        self.existing_combo.clear()
        for source_id in handbook_store.list_handbook_ids():
            label = f"{source_id}  (mine)" if handbook_store.is_user_handbook(source_id) \
                else f"{source_id}  (built-in)"
            self.existing_combo.addItem(label, source_id)
        self._update_delete_button()

    def _update_delete_button(self):
        source_id = self.existing_combo.currentData()
        self.delete_btn.setEnabled(bool(source_id) and handbook_store.is_user_handbook(source_id))

    def _read_key_values(self, source_id, names):
        """Stored values for the given credential names of an existing source."""
        values = {}
        for name in names:
            try:
                value = handbook_store.get_key_value(source_id, name)
            except Exception:
                value = ""
            if handbook_store.key_value_is_set(value):
                values[name] = value
        return values

    def _on_open_existing(self):
        source_id = self.existing_combo.currentData()
        path = handbook_store.handbook_file_for(source_id) if source_id else None
        if not path:
            return
        self._load_file(path, source_id)
        self._loaded_user_id = source_id if handbook_store.is_user_handbook(source_id) else ""

    def _on_import(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import a handbook", "", "TOML Files (*.toml)")
        if path:
            self._loaded_user_id = ""
            self._load_file(path, os.path.splitext(os.path.basename(path))[0])

    def _load_file(self, path, source_id):
        try:
            source = hg.load_toml_source(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Cannot read handbook", f"{os.path.basename(path)}:\n{e}")
            return
        self._fill_form(source, source_id=hg.make_source_id(source_id),
                        key_values=self._read_key_values(source_id, hg.split_key_names(source["key_name"])))
        self._chat_history = []
        self.chat_view.clear()
        self._log(f"Opened {path}")

    def _on_delete(self):
        source_id = self.existing_combo.currentData()
        if not source_id or not handbook_store.is_user_handbook(source_id):
            return
        if QtWidgets.QMessageBox.question(
                self, "Delete handbook",
                f"Delete your handbook '{source_id}'? Its saved API key is deleted too.") != QtWidgets.QMessageBox.Yes:
            return
        for path in (os.path.join(handbook_store.User_handbooks_dir, f"{source_id}.toml"),
                     os.path.join(handbook_store.User_keys_dir, f"{source_id}.keys")):
            if os.path.exists(path):
                os.remove(path)
        self._log(f"Deleted handbook '{source_id}'.")
        self._refresh_existing()
        self.handbook_saved.emit(source_id)

    # ── Saving ───────────────────────────────────────────────────────────
    def _on_save(self):
        self._suggest_id()
        source_id = self._source_id()
        source = self._current_source()
        missing = [label for label, key in (("Data source name", "data_source_name"),
                                            ("Brief description", "brief_description"),
                                            ("Handbook", "handbook")) if not source[key]]
        if not source_id:
            missing.insert(0, "Source ID")
        if missing:
            QtWidgets.QMessageBox.warning(self, "Missing information",
                                          "Please fill in: " + ", ".join(missing))
            return

        key_names = hg.split_key_names(source["key_name"])
        if source["requires_key"] == "true" and not key_names:
            QtWidgets.QMessageBox.warning(self, "Missing information",
                                          "Enter the key name(s) the data source needs, e.g. FIRMS_MAP_KEY.")
            return

        warnings = []
        code_env = {n.lower() for n in hg.env_names_in_code(source["code_example"])}
        handbook_lower = source["handbook"].lower()
        unused = [n for n in key_names
                  if n.lower() not in code_env and "{" + n.lower() + "}" not in handbook_lower]
        if unused:
            warnings.append(f"{', '.join(unused)} is neither read with os.environ[...] in the code example "
                            "nor written as {NAME} in the handbook, so the AI may not know how to use it.")
        if source["code_example"].strip() and "{code_example}" not in source["handbook"]:
            warnings.append("The handbook has no {code_example} line, so the AI will not see the code example.")
        if source_id != self._loaded_user_id:
            if handbook_store.is_user_handbook(source_id):
                warnings.append(f"You already have a handbook named '{source_id}'; it will be replaced.")
            elif handbook_store.handbook_file_for(source_id):
                warnings.append(f"'{source_id}' is a built-in data source; your handbook will be used instead of it.")
        for other_id in handbook_store.list_handbook_ids():
            if other_id == source_id:
                continue
            try:
                other = hg.load_toml_source(handbook_store.handbook_file_for(other_id))
            except Exception:
                continue
            if other["data_source_name"].strip().lower() == source["data_source_name"].lower():
                warnings.append(f"'{other_id}' already uses the name '{source['data_source_name']}'. "
                                "Names must be unique for the AI to tell sources apart.")
        if warnings and QtWidgets.QMessageBox.question(
                self, "Save anyway?", "\n\n".join(warnings) + "\n\nSave anyway?") != QtWidgets.QMessageBox.Yes:
            return

        text = hg.to_toml(source)
        try:
            try:
                import tomllib as _toml
            except ImportError:
                import tomli as _toml
            _toml.loads(text)  # never write a file the agent cannot read
            handbook_store.ensure_user_dirs()
            with open(os.path.join(handbook_store.User_handbooks_dir, f"{source_id}.toml"), "w",
                      encoding="utf-8") as fh:
                fh.write(text)
            keys_path = os.path.join(handbook_store.User_keys_dir, f"{source_id}.keys")
            if source["requires_key"] == "true":
                values = self._key_values()
                handbook_store.write_keys_file(source_id, {n: values.get(n, "") for n in key_names},
                                               source["key_signup_url"] or source["website"])
            elif os.path.exists(keys_path):
                os.remove(keys_path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))
            return

        self._loaded_user_id = source_id
        self._fill_form(source)
        self._refresh_existing()
        self._log(f"Saved handbook '{source_id}'. It is now available to the agent.")
        self.status_label.setText(f"<span style='color:#2e7d32'>Saved '{source_id}'.</span>")
        self.handbook_saved.emit(source_id)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        super().closeEvent(event)
