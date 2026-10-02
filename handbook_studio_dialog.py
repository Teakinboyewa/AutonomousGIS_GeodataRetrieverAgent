# -*- coding: utf-8 -*-
"""
Handbook Studio: create a data-source handbook with AI or by hand.

The window walks through three steps:
  1. Start      - "Generate with AI" (describe the source; the AI researches
                  it, drafts the handbook and can test its code example), or
                  "Write manually" (start blank, open an existing data source,
                  or import a .toml file).
  2. Refine     - chat with the AI to change the draft or fix an error.
  3. Review & save - one editable form (Overview / Handbook / Code example /
                  API keys), tested and saved to the user handbook folder
                  (outside the plugin, so it survives plugin updates).
"""
import html
import os
import re
import sys

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QThread, QUrl, pyqtSignal, QRegExp
from qgis.PyQt.QtGui import QDesktopServices, QFont, QRegExpValidator
from qgis.gui import QgsPasswordLineEdit

from . import llm_find_loader
from .data_sources_panel import _svg_pixmap
from .debug_support import debug_this_thread

handbook_store = llm_find_loader.load('handbook')
hg = llm_find_loader.load('handbook_generator')


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

ACCENT = "#2c5f7c"

_EXAMPLES = [
    ("NASA FIRMS", "NASA FIRMS active fire detections (MODIS/VIIRS)"),
    ("USGS streamflow", "USGS Water Services: real-time and daily streamflow at gauges in the US"),
    ("OpenAQ", "OpenAQ global air quality measurements (PM2.5, NO2, O3)"),
]

_STEPS = [
    ("Find the official source", "Searches for the best public source for your request"),
    ("Read the documentation", "Works out endpoints, parameters and authentication"),
    ("Write the handbook", "Drafts the requirements and a runnable code example"),
    ("Test the code example", "Runs a small sample download and fixes failures"),
]

_STEP_ICONS = {  # state -> (symbol, color)
    "pending": ("○", "#b9c2c8"),
    "running": ("◔", ACCENT),
    "done": ("✔", "#1a7f37"),
    "warning": ("!", "#9a6300"),
    "error": ("✖", "#a31b1b"),
    "skipped": ("–", "#9aa7af"),
}

_BANNER_STYLES = {  # kind -> (text color, background, border)
    "info": ("#3d4b55", "#eef3f6", "#dbe4ea"),
    "busy": (ACCENT, "#eef5f9", "#cfe0ea"),
    "success": ("#1a7f37", "#e6f4ea", "#b7dfc4"),
    "warning": ("#9a6300", "#fff4e0", "#f3d9a6"),
    "error": ("#a31b1b", "#fce8e8", "#efc0c0"),
}

_SPARKLE_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
                'stroke="#ffffff" stroke-width="2" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9.5 '
                '13.9 11.4 12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3z"/><path d="M19 14l.8 2 .2.05L22 17l-2 .95-.8 '
                '2-.8-2L16 17l2-.95.8-2z"/></svg>')

_STYLE = f"""
QDialog#HandbookStudio {{ background: #f4f6f8; }}
QFrame#Card {{ background: #ffffff; border: 1px solid #e3e8ec; border-radius: 10px; }}
QFrame#OptionRow {{ background: #fafbfc; border: 1px solid #e3e8ec; border-radius: 8px; }}
QLabel {{ color: #1f2d3a; background: transparent; }}
QLabel[role="title"] {{ font-size: 16pt; font-weight: 700; }}
QLabel[role="subtitle"] {{ color: #74838c; font-size: 9pt; }}
QLabel[role="hint"] {{ color: #74838c; font-size: 8pt; }}
QLabel[role="section"] {{ font-size: 11pt; font-weight: 700; }}
QLabel[role="field"] {{ font-weight: 600; color: #3d4b55; }}
QLabel[role="num"] {{ background: {ACCENT}; color: #ffffff; border-radius: 11px; font-weight: 700;
                      min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }}
QLineEdit, QPlainTextEdit, QTextBrowser {{ background: #ffffff; border: 1px solid #d5dde3; border-radius: 6px;
                                          padding: 4px 6px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QPlainTextEdit:disabled {{ background: #f4f6f8; color: #9aa7af; }}
QPushButton {{ border: 1px solid #c9d3da; border-radius: 6px; padding: 6px 14px; background: #ffffff;
               color: #1f2d3a; }}
QPushButton:hover {{ background: #eef3f6; }}
QPushButton:disabled {{ color: #a9b4bb; background: #f4f6f8; border-color: #e3e8ec; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: #ffffff; border: 1px solid {ACCENT}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: #244e66; }}
QPushButton[kind="primary"]:disabled {{ background: #a7bccb; border-color: #a7bccb; color: #f4f6f8; }}
QPushButton[kind="danger"] {{ color: #a31b1b; }}
QPushButton[kind="danger"]:hover {{ background: #f6e9e9; }}
QPushButton[kind="danger"]:disabled {{ color: #c9b1b1; }}
QPushButton[kind="link"] {{ border: none; background: transparent; color: {ACCENT}; padding: 2px 4px; }}
QPushButton[kind="link"]:hover {{ text-decoration: underline; }}
QPushButton[kind="chip"] {{ border-radius: 11px; padding: 3px 10px; background: #eef3f6; border: 1px solid #dbe4ea;
                            color: {ACCENT}; }}
QPushButton[kind="chip"]:hover {{ background: #e1ebf1; }}
QPushButton[kind="mode"] {{ text-align: left; padding: 10px 12px; border-radius: 8px; border: 1px solid #d5dde3; }}
QPushButton[kind="mode"]:checked {{ border: 2px solid {ACCENT}; background: #eef5f9; }}
QCheckBox {{ color: #1f2d3a; }}
QTabWidget::pane {{ border: 1px solid #e3e8ec; border-radius: 8px; background: #ffffff; top: -1px; }}
QTabBar::tab {{ background: #eef1f3; color: #5b6b75; border: 1px solid #e3e8ec; border-bottom: none;
                padding: 6px 14px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; }}
QTabBar::tab:selected {{ background: #ffffff; color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QTabWidget#StepTabs::pane {{ background: #f4f6f8; border: none; border-top: 1px solid #dbe4ea; top: -1px; }}
QTabWidget#StepTabs > QTabBar::tab {{ background: transparent; color: #5b6b75; border: none;
    border-bottom: 3px solid transparent; padding: 9px 22px; margin-right: 4px; font-size: 11pt; }}
QTabWidget#StepTabs > QTabBar::tab:hover {{ color: {ACCENT}; }}
QTabWidget#StepTabs > QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 3px solid {ACCENT}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
"""


def _set_props(widget, **props):
    for name, value in props.items():
        widget.setProperty(name, value)
    return widget


def _label(text, role=None, wrap=False):
    label = QtWidgets.QLabel(text)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    if wrap:
        # A long unbreakable word (e.g. a file path) must not widen the window
        label.setMinimumWidth(60)
    return label


def _button(text, kind=None, tooltip=None):
    button = QtWidgets.QPushButton(text)
    if kind:
        button.setProperty("kind", kind)
    if tooltip:
        button.setToolTip(tooltip)
    button.setCursor(Qt.PointingHandCursor)
    return button


def _card():
    frame = QtWidgets.QFrame()
    frame.setObjectName("Card")
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 14)
    layout.setSpacing(8)
    return frame, layout


def _section_header(number, title, subtitle=None):
    row = QtWidgets.QHBoxLayout()
    row.setSpacing(8)
    if number:
        num = _label(str(number), "num")
        num.setAlignment(Qt.AlignCenter)
        row.addWidget(num, 0, Qt.AlignTop)
    text = QtWidgets.QVBoxLayout()
    text.setSpacing(0)
    text.addWidget(_label(title, "section"))
    if subtitle:
        text.addWidget(_label(subtitle, "hint", wrap=True))
    row.addLayout(text, 1)
    return row


def _field(label, widget, hint=None):
    """A form field: bold label above the input, optional grey hint below."""
    box = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    layout.addWidget(_label(label, "field"))
    layout.addWidget(widget)
    if hint:
        layout.addWidget(_label(hint, "hint", wrap=True))
    return box


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
        debug_this_thread()
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
        self.setObjectName("HandbookStudio")
        self.setWindowTitle("Handbook Studio - Add a New Data Source")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setStyleSheet(_STYLE)
        self.resize(1240, 860)
        self._settings_provider = settings_provider
        self._python_exe = python_exe
        self._worker = None
        self._chat_history = []
        self._loaded_user_id = ""    # user handbook currently being edited
        self._step_states = ["pending"] * len(_STEPS)
        self._generating = False
        self._build_ui()
        self._refresh_existing()
        self._update_key_widgets()
        self._set_status("Start by generating a handbook with AI, or write one manually.", "info")

    # ── UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        # The three steps as tabs: Start - Refine with AI - Review & Save
        self.step_tabs = QtWidgets.QTabWidget()
        self.step_tabs.setObjectName("StepTabs")
        self.step_tabs.addTab(self._build_start_tab(), "1   Start")
        self.step_tabs.addTab(self._build_refine_tab(), "2   Refine with AI")
        self.step_tabs.addTab(self._build_form_panel(), "3   Review && Save")
        root.addWidget(self.step_tabs, 1)
        root.addLayout(self._build_footer())

    def _build_header(self):
        icon = QtWidgets.QLabel()
        icon.setPixmap(_svg_pixmap(_SPARKLE_SVG, 44, background=ACCENT, radius=11))
        title = _label("Handbook Studio", "title")
        subtitle = _label("Teach the agent a new data source. Describe it and let AI write the handbook, "
                          "or write it yourself; then test and save it.", "subtitle", wrap=True)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(title)
        text.addWidget(subtitle)
        self.backend_pill = QtWidgets.QLabel()
        self.backend_pill.setAlignment(Qt.AlignCenter)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(icon, 0, Qt.AlignTop)
        header.addLayout(text, 1)
        header.addWidget(self.backend_pill, 0, Qt.AlignTop)
        return header

    def _build_footer(self):
        self.folder_label = _label("", "hint")
        self.folder_label.setText(f"Your handbooks are saved in {handbook_store.User_handbooks_dir}")
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_folder = _button("Open folder", "link")
        open_folder.clicked.connect(self._open_user_folder)
        close_btn = _button("Close")
        close_btn.clicked.connect(self.close)
        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(self.folder_label)
        footer.addWidget(open_folder)
        footer.addStretch(1)
        footer.addWidget(close_btn)
        return footer

    def _build_start_tab(self):
        """Step 1: how to start (left) and the generation progress (right)."""
        page = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(page)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)
        row.addWidget(self._build_start_card(), 3)
        row.addWidget(self._build_progress_card(), 2, Qt.AlignTop)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _build_refine_tab(self):
        """Step 2: the chat with the AI about the current draft."""
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.addWidget(self._build_refine_card(), 1)
        return page

    # Step 1: start ---------------------------------------------------------
    def _build_start_card(self):
        card, v = _card()
        v.addLayout(_section_header(None, "How do you want to create the handbook?"))

        self.ai_mode_btn = _button("✨  Generate with AI\nAI writes it for you", "mode")
        self.manual_mode_btn = _button("✎  Write manually\nBlank, edit or import", "mode")
        modes = QtWidgets.QHBoxLayout()
        self._mode_group = QtWidgets.QButtonGroup(self)
        for index, button in enumerate((self.ai_mode_btn, self.manual_mode_btn)):
            button.setCheckable(True)
            button.setMinimumHeight(54)
            self._mode_group.addButton(button, index)
            modes.addWidget(button)
        v.addLayout(modes)

        self.mode_tabs = QtWidgets.QStackedWidget()
        self.mode_tabs.addWidget(self._build_ai_page())
        self.mode_tabs.addWidget(self._build_manual_page())
        self._mode_group.buttonClicked[int].connect(self.mode_tabs.setCurrentIndex)
        self.mode_tabs.currentChanged.connect(self._on_mode_changed)
        self.ai_mode_btn.setChecked(True)
        self._on_mode_changed(0)
        v.addWidget(self.mode_tabs)
        v.addStretch(1)  # spare height goes below the content, not between its parts
        return card

    def _build_ai_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(8)

        self.request_edit = QtWidgets.QPlainTextEdit()
        self.request_edit.setPlaceholderText(
            "e.g. 'Hourly air temperature from NOAA weather stations', a provider name, or paste an API link")
        self.request_edit.setFixedHeight(74)
        v.addWidget(_field("What data source or data do you need?", self.request_edit))

        chips = QtWidgets.QHBoxLayout()
        chips.setSpacing(6)
        chips.addWidget(_label("Try:", "hint"))
        for title, text in _EXAMPLES:
            chip = _button(title, "chip", f"Use the example: {text}")
            chip.clicked.connect(lambda _=False, t=text: self.request_edit.setPlainText(t))
            chips.addWidget(chip)
        chips.addStretch(1)
        v.addLayout(chips)

        self.website_edit = QtWidgets.QLineEdit()
        self.website_edit.setPlaceholderText("https://... (optional)")
        v.addWidget(_field("Website or documentation link", self.website_edit,
                           "Optional. Helps the AI find the right API."))

        self.verify_check = QtWidgets.QCheckBox("Test the code and let the AI fix failures")
        self.verify_check.setChecked(True)
        self.verify_check.setToolTip("Runs the code example as a small sample download in a separate "
                                     "Python process; failures are sent back to the AI to fix (up to 6 tries).")
        v.addWidget(self.verify_check)

        self.backend_label = _label("", "hint", wrap=True)
        v.addWidget(self.backend_label)

        buttons = QtWidgets.QHBoxLayout()
        self.generate_btn = _button("✨  Generate handbook", "primary")
        self.generate_btn.setMinimumHeight(34)
        self.generate_btn.clicked.connect(self._on_generate)
        self.stop_btn = _button("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        buttons.addWidget(self.generate_btn, 1)
        buttons.addWidget(self.stop_btn)
        v.addLayout(buttons)
        return page

    def _option_row(self, title, hint, controls):
        frame = QtWidgets.QFrame()
        frame.setObjectName("OptionRow")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addWidget(_label(title, "field"))
        layout.addWidget(_label(hint, "hint", wrap=True))
        row = QtWidgets.QHBoxLayout()
        for widget, stretch in controls:
            row.addWidget(widget, stretch)
        layout.addLayout(row)
        return frame

    def _build_manual_page(self):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(8)

        blank_btn = _button("Start a blank handbook")
        blank_btn.clicked.connect(self._on_blank)
        v.addWidget(self._option_row("Start from scratch",
                                     "A blank form with the required lines and a code template.",
                                     [(blank_btn, 0), (QtWidgets.QWidget(), 1)]))

        self.existing_combo = QtWidgets.QComboBox()
        self.existing_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.existing_combo.setMinimumContentsLength(14)
        self.existing_combo.currentIndexChanged.connect(self._update_delete_button)
        open_btn = _button("Open")
        open_btn.clicked.connect(self._on_open_existing)
        self.delete_btn = _button("Delete", "danger", "Delete one of your own handbooks")
        self.delete_btn.clicked.connect(self._on_delete)
        v.addWidget(self._option_row("Edit an existing data source",
                                     "Editing a built-in data source saves your own copy, which then "
                                     "replaces the built-in one for you.",
                                     [(self.existing_combo, 1), (open_btn, 0), (self.delete_btn, 0)]))

        import_btn = _button("Import a .toml file...")
        import_btn.clicked.connect(self._on_import)
        v.addWidget(self._option_row("Import a handbook file",
                                     "For example one shared by a colleague or downloaded from a data source card.",
                                     [(import_btn, 0), (QtWidgets.QWidget(), 1)]))
        return page

    # Progress ----------------------------------------------------------------
    def _build_progress_card(self):
        card, v = _card()
        v.addLayout(_section_header(None, "Progress"))

        self.steps_widget = QtWidgets.QWidget()
        steps = QtWidgets.QVBoxLayout(self.steps_widget)
        steps.setContentsMargins(0, 0, 0, 0)
        steps.setSpacing(4)
        self._step_icons, self._step_titles = [], []
        for title, hint in _STEPS:
            icon = QtWidgets.QLabel()
            icon.setFixedWidth(18)
            icon.setAlignment(Qt.AlignCenter)
            name = _label(title)
            name.setToolTip(hint)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(icon)
            row.addWidget(name, 1)
            steps.addLayout(row)
            self._step_icons.append(icon)
            self._step_titles.append(name)
        v.addWidget(self.steps_widget)
        self._render_steps()

        self.activity_label = _label("Nothing is running.", "hint", wrap=True)
        v.addWidget(self.activity_label)

        self.details_btn = _button("Show details", "link")
        self.details_btn.setCheckable(True)
        self.details_btn.toggled.connect(self._toggle_details)
        v.addWidget(self.details_btn, 0, Qt.AlignLeft)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(120)
        self.log_view.setVisible(False)
        v.addWidget(self.log_view)
        return card

    # Step 2: refine -------------------------------------------------------
    def _build_refine_card(self):
        card, v = _card()
        v.addLayout(_section_header(None, "Refine the draft with AI",
                                    "Ask for a change, or paste an error you got when using the handbook. "
                                    "Changes are applied to the draft in Review & Save."))
        self.chat_view = QtWidgets.QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setMinimumHeight(110)
        self.chat_view.setPlaceholderText("Generate or open a handbook first, then tell the AI what to change.")
        v.addWidget(self.chat_view, 1)

        suggestions = QtWidgets.QHBoxLayout()
        suggestions.setSpacing(6)
        suggestions.addWidget(_label("Try:", "hint"))
        for text in ("Save the output as GeoJSON", "Handle pagination and rate limits",
                     "Make the example download smaller", "Add the license to the caveats"):
            chip = _button(text, "chip")
            chip.clicked.connect(lambda _=False, t=text: (self.refine_input.setText(t), self.refine_input.setFocus()))
            suggestions.addWidget(chip)
        suggestions.addStretch(1)
        v.addLayout(suggestions)
        row = QtWidgets.QHBoxLayout()
        self.refine_input = QtWidgets.QLineEdit()
        self.refine_input.setPlaceholderText("What should change?")
        self.refine_input.returnPressed.connect(self._on_refine)
        self.refine_btn = _button("Send", "primary")
        self.refine_btn.clicked.connect(self._on_refine)
        row.addWidget(self.refine_input, 1)
        row.addWidget(self.refine_btn)
        v.addLayout(row)
        return card

    # Step 3: review & save ----------------------------------------------
    def _build_form_panel(self):
        card, v = _card()
        v.addLayout(_section_header(None, "Review & save",
                                    "Check the handbook, edit anything you like, test the code, then save."))
        mono = QFont("Consolas" if sys.platform == "win32" else "Monospace")
        mono.setStyleHint(QFont.Monospace)

        self.form_tabs = QtWidgets.QTabWidget()
        self.form_tabs.setDocumentMode(False)

        # Overview
        overview = QtWidgets.QWidget()
        ov = QtWidgets.QVBoxLayout(overview)
        ov.setContentsMargins(12, 12, 12, 12)
        ov.setSpacing(10)
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g. NASA FIRMS Active Fires")
        self.name_edit.editingFinished.connect(self._suggest_id)
        self.id_edit = QtWidgets.QLineEdit()
        self.id_edit.setValidator(QRegExpValidator(QRegExp(r"[A-Za-z0-9_]{0,60}")))
        self.id_edit.setPlaceholderText("e.g. NASA_FIRMS")
        self.id_edit.textChanged.connect(self._update_key_widgets)
        names = QtWidgets.QHBoxLayout()
        names.setSpacing(10)
        names.addWidget(_field("Data source name *", self.name_edit, "Unique, human-readable name."), 3)
        names.addWidget(_field("Source ID *", self.id_edit, "File name: letters, digits, underscores."), 2)
        ov.addLayout(names)
        self.desc_edit = QtWidgets.QPlainTextEdit()
        self.desc_edit.setPlaceholderText("What data it offers, its extent and period.")
        self.desc_edit.setFixedHeight(86)
        ov.addWidget(_field("Brief description *", self.desc_edit,
                            "1-3 sentences. The agent reads this to decide when to use the source."))
        self.website_field = QtWidgets.QLineEdit()
        self.website_field.setPlaceholderText("https://...")
        ov.addWidget(_field("Website", self.website_field))
        self.caveats_edit = QtWidgets.QPlainTextEdit()
        self.caveats_edit.setPlaceholderText("Optional: rate limits, paid tiers, coverage gaps...")
        self.caveats_edit.setFixedHeight(64)
        ov.addWidget(_field("Caveats", self.caveats_edit))
        ov.addStretch(1)
        self.form_tabs.addTab(self._scroll_page(overview), "Overview")

        # Handbook
        handbook_page = QtWidgets.QWidget()
        hv = QtWidgets.QVBoxLayout(handbook_page)
        hv.setContentsMargins(12, 12, 12, 12)
        hv.addWidget(_label("Technical requirements for the agent, one per line: endpoints, parameters, formats, "
                            "pitfalls. Keep the line with {code_example} so the agent sees the code example.",
                            "hint", wrap=True))
        self.handbook_edit = QtWidgets.QPlainTextEdit()
        self.handbook_edit.setPlaceholderText("Technical requirements, one per line.")
        hv.addWidget(self.handbook_edit, 1)
        self.form_tabs.addTab(handbook_page, "Handbook")

        # Code example
        code_page = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(code_page)
        cv.setContentsMargins(12, 12, 12, 12)
        cv.addWidget(_label("A runnable script with a download_data() function that saves a small sample "
                            "to a file. 'Test code' runs it in a separate Python process.", "hint", wrap=True))
        self.code_edit = QtWidgets.QPlainTextEdit()
        self.code_edit.setFont(mono)
        self.code_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        cv.addWidget(self.code_edit, 1)
        try:  # same highlighter as the plugin's code editor
            from .AGGRA_dockwidget import PythonHighlighter
            self._code_highlighter = PythonHighlighter(self.code_edit.document(), always_highlight=True)
        except Exception:
            self._code_highlighter = None
        self.form_tabs.addTab(code_page, "Code example")

        # API keys
        keys_page = QtWidgets.QWidget()
        kv = QtWidgets.QVBoxLayout(keys_page)
        kv.setContentsMargins(12, 12, 12, 12)
        kv.setSpacing(10)
        self.requires_key_check = QtWidgets.QCheckBox("This data source needs an API key or other credentials")
        self.requires_key_check.toggled.connect(self._update_key_widgets)
        kv.addWidget(self.requires_key_check)
        self.key_name_edit = QtWidgets.QLineEdit()
        self.key_name_edit.setValidator(QRegExpValidator(QRegExp(r"[A-Za-z0-9_, ]*")))
        self.key_name_edit.setPlaceholderText("e.g. FIRMS_MAP_KEY  (comma-separated if several)")
        self.key_name_edit.textChanged.connect(self._rebuild_key_inputs)
        kv.addWidget(_field("Key names", self.key_name_edit,
                            "The provider's own name for each credential; one name per credential."))

        # One password field per credential name, rebuilt when the names change.
        self._key_inputs = {}
        self._key_values_cache = {}
        self.key_values_widget = QtWidgets.QWidget()
        self.key_values_form = QtWidgets.QFormLayout(self.key_values_widget)
        self.key_values_form.setContentsMargins(0, 0, 0, 0)
        self.key_values_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        kv.addWidget(self.key_values_widget)

        self.placeholder_label = _label("", "hint", wrap=True)
        self.placeholder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        kv.addWidget(self.placeholder_label)
        self.signup_edit = QtWidgets.QLineEdit()
        self.signup_edit.setPlaceholderText("https://... (optional)")
        kv.addWidget(_field("Key sign-up page", self.signup_edit, "Where users register for a key."))
        kv.addWidget(_label("Key values are stored only on this computer, in the data source's .keys file, "
                            "never in the handbook.", "hint", wrap=True))
        kv.addStretch(1)
        self.form_tabs.addTab(self._scroll_page(keys_page), "API keys")
        v.addWidget(self.form_tabs, 1)

        # Status banner + actions
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
        self.test_btn = _button("▶  Test code", tooltip="Run the code example once in a separate Python process")
        self.test_btn.clicked.connect(self._on_test)
        self.save_btn = _button("Save handbook", "primary")
        self.save_btn.setMinimumHeight(34)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        self.fix_btn = _button("✨  Fix with AI", tooltip="Send the error to the AI in 'Refine with AI'")
        self.fix_btn.clicked.connect(self._on_fix_with_ai)
        self.fix_btn.setVisible(False)
        v.addWidget(self.status_label)
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        actions.addWidget(self.fix_btn)
        actions.addWidget(self.test_btn)
        actions.addWidget(self.save_btn)
        v.addLayout(actions)

        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.addWidget(card)
        return page

    # ── Small UI helpers ─────────────────────────────────────────────────
    def _on_mode_changed(self, index):
        """Sync the mode buttons, and size the stack to the visible page only
        (otherwise the shorter page keeps the taller page's height)."""
        self._mode_group.button(index).setChecked(True)
        for i in range(self.mode_tabs.count()):
            policy = QtWidgets.QSizePolicy.Preferred if i == index else QtWidgets.QSizePolicy.Ignored
            self.mode_tabs.widget(i).setSizePolicy(QtWidgets.QSizePolicy.Preferred, policy)
        self.mode_tabs.setMaximumHeight(self.mode_tabs.widget(index).sizeHint().height())
        self.mode_tabs.adjustSize()

    def _go_to(self, step):
        """Switch to a step tab: 0 Start, 1 Refine with AI, 2 Review & Save."""
        self.step_tabs.setCurrentIndex(step)

    def _on_fix_with_ai(self):
        self._go_to(1)
        self.refine_input.setFocus()

    @staticmethod
    def _scroll_page(page):
        """Wrap a form tab so its fields scroll instead of being squeezed."""
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _set_status(self, text, kind="info"):
        if hasattr(self, "fix_btn") and kind != "error":
            self.fix_btn.setVisible(False)
        fg, bg, border = _BANNER_STYLES.get(kind, _BANNER_STYLES["info"])
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"QLabel {{ color: {fg}; background: {bg}; border: 1px solid {border}; "
                                        f"border-radius: 6px; padding: 6px 10px; }}")
        self._status_kind = kind

    def _render_steps(self):
        for icon, title, state in zip(self._step_icons, self._step_titles, self._step_states):
            symbol, color = _STEP_ICONS[state]
            icon.setText(symbol)
            icon.setStyleSheet(f"color: {color}; font-weight: 700;")
            muted = state in ("pending", "skipped")
            title.setStyleSheet(f"color: {'#9aa7af' if muted else '#1f2d3a'};"
                                f"{' font-weight: 600;' if state == 'running' else ''}")

    def _set_step(self, index, state):
        if 0 <= index < len(self._step_states):
            self._step_states[index] = state
            self._render_steps()

    def _track_progress(self, line):
        """Follow the generator's 'Step k/4' messages on the checklist."""
        match = re.search(r"Step (\d)/4", line)
        if match:
            k = int(match.group(1)) - 1
            for i in range(k):
                if self._step_states[i] in ("pending", "running"):
                    self._step_states[i] = "done"
            self._step_states[k] = "skipped" if "skipped" in line.lower() else "running"
            self._render_steps()

    def _toggle_details(self, shown):
        self.log_view.setVisible(shown)
        self.details_btn.setText("Hide details" if shown else "Show details")

    def _chat_append(self, role, text):
        body = html.escape(text).replace("\n", "<br>")
        if role == "user":
            bubble = (f"<table width='100%' cellspacing='0' cellpadding='8'><tr><td width='15%'></td>"
                      f"<td bgcolor='#e6f0f6'><b style='color:{ACCENT}'>You</b><br>{body}</td></tr></table>")
        else:
            bubble = (f"<table width='100%' cellspacing='0' cellpadding='8'><tr>"
                      f"<td bgcolor='#f4f6f8'><b style='color:#3b7a57'>AI</b><br>{body}</td>"
                      f"<td width='15%'></td></tr></table>")
        self.chat_view.append(bubble)
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def _open_user_folder(self):
        handbook_store.ensure_user_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(handbook_store.User_handbooks_dir))

    def _update_form_tab_titles(self):
        if not hasattr(self, "form_tabs"):
            return
        missing = self.requires_key_check.isChecked() and (
            not self._key_names() or any(not self._key_values_cache.get(n) for n in self._key_names()))
        self.form_tabs.setTabText(3, "API keys  ⚠" if missing else "API keys")
        self.form_tabs.setTabToolTip(3, "A key name or value is missing" if missing else "")

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
            edit.setPlaceholderText("Your value")
            edit.setText(self._key_values_cache.get(name, ""))
            edit.setEnabled(self.requires_key_check.isChecked())
            edit.textChanged.connect(lambda _=None: (self._sync_key_cache(), self._update_form_tab_titles()))
            self._key_inputs[name] = edit
            label = _label(f"{name}", "field")
            self.key_values_form.addRow(label, edit)
        self._update_placeholder_help()
        self._update_form_tab_titles()

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
        self._update_form_tab_titles()

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
            pill = ("●  No AI key set", "#a31b1b", "#fce8e8", "#efc0c0")
        elif "gibd-services" in key:
            text = ("Using your GIBD key: the AI cannot search the web, so it relies on its own knowledge "
                    "and on documentation links you give it. Adding the documentation link helps a lot.")
            pill = ("●  GIBD key · no web search", "#9a6300", "#fff4e0", "#f3d9a6")
        else:
            text = "Using your OpenAI key: the AI will search the web for the official documentation."
            pill = ("●  OpenAI key · web search", "#1a7f37", "#e6f4ea", "#b7dfc4")
        self.backend_label.setText(text)
        self.backend_pill.setText(pill[0])
        self.backend_pill.setToolTip(text + "\nThe AI key and model are set in the plugin's Settings tab.")
        self.backend_pill.setStyleSheet(f"QLabel {{ color: {pill[1]}; background: {pill[2]}; "
                                        f"border: 1px solid {pill[3]}; border-radius: 12px; padding: 4px 12px; "
                                        f"font-weight: 600; }}")

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
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        if first_line and not first_line.startswith("Last error"):
            self.activity_label.setText(first_line)
        if self._generating:
            self._track_progress(text)

    def _set_busy(self, busy):
        for w in (self.generate_btn, self.refine_btn, self.test_btn, self.save_btn, self.refine_input,
                  self.ai_mode_btn, self.manual_mode_btn):
            w.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        if busy:
            self._set_status("Working... you can keep reading the draft meanwhile.", "busy")
        elif getattr(self, "_status_kind", "") == "busy":
            self._set_status("Done.", "info")
        if not busy:
            self._generating = False

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
        if self._generating and "running" in self._step_states:
            self._set_step(self._step_states.index("running"), "error")
        self._set_status(message if len(message) < 200 else message[:200] + "...",
                         "warning" if message == "Stopped." else "error")

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
            self.request_edit.setFocus()
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
        self._step_states = ["pending"] * len(_STEPS)
        self._render_steps()
        self._generating = True

        def job(log, should_stop):
            return hg.generate_handbook(query, backend, website=website, verify=verify,
                                        python_exe=python_exe, keys=keys,
                                        log=log, should_stop=should_stop)
        self._start(job, self._on_generated)

    def _on_generated(self, result):
        source_id, source, report = result
        self._loaded_user_id = ""
        for i in range(3):
            self._step_states[i] = "done"
        self._render_steps()
        self._fill_form(source, source_id=source_id)
        self.form_tabs.setCurrentIndex(0)
        self._go_to(2)
        if report is None:
            self._set_step(3, "skipped")
            self._set_status("Draft ready. Review it, then press 'Test code' or 'Save handbook'.", "info")
        self._show_report(report)

    def _show_report(self, report):
        if not report:
            return
        status = report.get("status")
        if status == "verified":
            self._set_step(3, "done")
            self._set_status("Tested: the sample download worked. Review the handbook, then save it.", "success")
        elif status == "skipped_needs_key":
            self._set_step(3, "warning")
            missing = ", ".join(report.get("missing") or []) or "the API key"
            self._set_status(f"Not tested yet: enter a value for {missing} in the API keys tab, "
                             "then press 'Test code'.", "warning")
            self.form_tabs.setCurrentIndex(3)
        else:
            self._set_step(3, "error")
            err = (report.get("error") or "").strip()
            last_line = err.splitlines()[-1] if err else ""
            self._set_status("The code example failed" + (f": {last_line[:160]}" if last_line else ".")
                             + "  Click 'Fix with AI' to send the error to the AI.", "error")
            if err:
                self._log("Last error:\n" + err[-1500:])
                self.status_label.setToolTip(err[-1500:])
                tail = "\n".join(err.splitlines()[-6:])
                self.refine_input.setText(f"The code example failed with this error, please fix it: {tail}")
                self.fix_btn.setVisible(True)

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
        self._chat_append("user", message)
        self._chat_history.append({"role": "user", "content": message})
        self.refine_input.clear()

        def job(log, should_stop):
            log("Asking the AI to revise the handbook...")
            return hg.refine_handbook(current, message, backend, source_id, history=history, log=log)

        def done(result):
            source, reply = result
            self._fill_form(source, source_id=source_id)
            self._chat_append("assistant", reply)
            self._chat_history.append({"role": "assistant", "content": reply})
            self._log("Handbook revised. Press 'Test code' to check it.")
            self._set_status("Handbook revised. Press 'Test code' to check it.", "info")
        self._start(job, done)

    # ── Testing ──────────────────────────────────────────────────────────
    def _on_test(self):
        source = self._current_source()
        source_id = self._source_id()
        if not source["code_example"].strip():
            QtWidgets.QMessageBox.information(self, "No code", "There is no code example to test.")
            self.form_tabs.setCurrentIndex(2)
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
        self.form_tabs.setCurrentIndex(0)
        self._go_to(2)
        self._set_status("Blank handbook ready. Fill in the Overview, Handbook and Code example tabs.", "info")
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

    def open_source(self, source_id):
        """Open an existing data source for editing (used by the Data Sources cards)."""
        self._refresh_existing()
        index = self.existing_combo.findData(source_id)
        if index < 0:
            return
        self.existing_combo.setCurrentIndex(index)
        self.mode_tabs.setCurrentIndex(1)
        self._on_open_existing()

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
        self.form_tabs.setCurrentIndex(0)
        self._go_to(2)
        self._log(f"Opened {path}")
        self._set_status(f"Opened '{source['data_source_name'] or source_id}'. Edit it, then save.", "info")

    def _on_delete(self):
        source_id = self.existing_combo.currentData()
        if not source_id or not handbook_store.is_user_handbook(source_id):
            return
        if QtWidgets.QMessageBox.question(
                self, "Delete handbook",
                f"Delete your handbook '{source_id}'? Its saved API key is deleted too.") != QtWidgets.QMessageBox.Yes:
            return
        handbook_store.delete_user_handbook(source_id)
        self._log(f"Deleted handbook '{source_id}'.")
        self._set_status(f"Deleted '{source_id}'.", "info")
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
            self.form_tabs.setCurrentIndex(1 if missing == ["Handbook"] else 0)
            return

        key_names = hg.split_key_names(source["key_name"])
        if source["requires_key"] == "true" and not key_names:
            QtWidgets.QMessageBox.warning(self, "Missing information",
                                          "Enter the key name(s) the data source needs, e.g. FIRMS_MAP_KEY.")
            self.form_tabs.setCurrentIndex(3)
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
        self._set_status(f"Saved '{source_id}'. The agent can now use this data source.", "success")
        self.handbook_saved.emit(source_id)

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        super().closeEvent(event)
