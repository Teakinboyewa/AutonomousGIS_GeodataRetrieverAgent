# -*- coding: utf-8 -*-
"""
Data Sources tab: the available data sources shown as cards (the same design
as the Data Sources panel of GIS Co-Scientist), with a details window.

Each card has a colored left accent and avatar (the color is derived from the
source name, so a source always gets the same hue), the name, a two-line
description, badges (Built-in / Mine / Customized, and the API key status),
and Download / Delete actions.
"""
import html
import os
import re
import shutil

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt, QByteArray, QEvent, QRectF, QSize, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer

from . import llm_find_loader

handbook_store = llm_find_loader.load('handbook')

# Professional palette for per-card color accents (same as GIS Co-Scientist).
CARD_PALETTE = ['#2c5f7c', '#3b7a57', '#8a5a2b', '#6a4c93', '#1b6e8c',
                '#9c4f4f', '#4f7a3b', '#b5762a', '#3d5a80', '#5c6bc0']

CARD_MIN_WIDTH = 260
CARD_HEIGHT = 60

_DB_ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
                'stroke="#ffffff" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/>'
                '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/></svg>')
_DOWNLOAD_ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
                      'stroke="{color}" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                      '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>')

# Badge styles: (text color, background, border)
_BADGES = {
    "builtin": ("#5b6b75", "#eef1f3", "#dde3e7"),
    "mine": ("#1a7f37", "#e6f4ea", "#b7dfc4"),
    "custom": ("#9a6300", "#fff4e0", "#f3d9a6"),
    "key_ok": ("#1a7f37", "#e6f4ea", "#b7dfc4"),
    "key_missing": ("#a31b1b", "#fce8e8", "#efc0c0"),
}


def card_color(name):
    """Deterministic color from a source name (same hash as GIS Co-Scientist)."""
    h = 0
    for ch in str(name or ""):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return CARD_PALETTE[h % len(CARD_PALETTE)]


def _svg_pixmap(svg, size, background=None, radius=9):
    """Render an SVG icon to a pixmap, optionally on a rounded colored square."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    inset = 0
    if background:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
        inset = size * 0.23
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(
        painter, QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    painter.end()
    return pixmap


def _elide_lines(text, metrics, width, max_lines):
    """Wrap ``text`` to ``width`` pixels and keep at most ``max_lines`` lines,
    ending with an ellipsis when cut."""
    words, lines, current = text.split(), [], ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if metrics.horizontalAdvance(candidate) <= width or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            rest = " ".join([current] + words[i + 1:])
            lines.append(metrics.elidedText(rest, Qt.ElideRight, width))
            return "\n".join(lines)
    if current:
        lines.append(metrics.elidedText(current, Qt.ElideRight, width))
    return "\n".join(lines[:max_lines])


class _ElidedLabel(QtWidgets.QLabel):
    """A label that clips its text to a number of lines with an ellipsis."""

    def __init__(self, text, max_lines=1, parent=None):
        super().__init__(parent)
        self._full_text = text
        self._max_lines = max_lines
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(10, self.width())
        if self._max_lines == 1:
            self.setText(self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width))
        else:
            self.setText(_elide_lines(self._full_text, self.fontMetrics(), width, self._max_lines))


def _badge(text, kind):
    fg, bg, border = _BADGES[kind]
    label = QtWidgets.QLabel(text.upper())
    font = label.font()
    font.setPointSizeF(max(6.0, font.pointSizeF() * 0.72))
    font.setBold(True)
    label.setFont(font)
    label.setStyleSheet(f"QLabel {{ color: {fg}; background: {bg}; border: 1px solid {border}; "
                        f"border-radius: 8px; padding: 0px 6px; }}")
    label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)  # never clip the text
    return label


class DataSourceCard(QtWidgets.QFrame):
    """One data source card."""
    opened = pyqtSignal(dict)
    download_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        color = card_color(info["name"] or info["id"])
        self.setObjectName("dsCard")
        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedHeight(CARD_HEIGHT)
        self.setMinimumWidth(CARD_MIN_WIDTH - 20)
        self.setToolTip(f"<b>{html.escape(info['name'] or info['id'])}</b><br>"
                        f"{html.escape(info['description'][:300])}<br><i>Click to view details</i>")
        self.setStyleSheet(
            f"QFrame#dsCard {{ background: #ffffff; border: 1px solid #e3e8ec; border-left: 4px solid {color}; "
            f"border-radius: 10px; }}"
            f"QFrame#dsCard:hover, QFrame#dsCard:focus {{ border: 1px solid {color}; border-left: 4px solid {color}; }}")

        avatar = QtWidgets.QLabel()
        avatar.setPixmap(_svg_pixmap(_DB_ICON_SVG, 28, background=color, radius=7))
        avatar.setFixedSize(28, 28)

        name = _ElidedLabel(info["name"] or info["id"], 1)
        name_font = name.font()
        name_font.setBold(True)
        name.setFont(name_font)
        name.setStyleSheet(f"color: {color}; background: transparent; border: none;")

        desc = _ElidedLabel(info["description"] or "No description", 1)
        desc_font = desc.font()
        desc_font.setPointSizeF(desc_font.pointSizeF() * 0.9)
        desc.setFont(desc_font)
        desc.setStyleSheet("color: #74838c; background: transparent; border: none;")
        desc.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # Top-right actions: Download (always visible) + Delete (own sources, on hover).
        self.download_btn = QtWidgets.QToolButton()
        self.download_btn.setIcon(self._icon(_DOWNLOAD_ICON_SVG.format(color="#9aa7af")))
        self.download_btn.setIconSize(QSize(14, 14))
        self.download_btn.setToolTip("Download this data source (.toml)")
        self.download_btn.setAutoRaise(True)
        self.download_btn.setCursor(Qt.ArrowCursor)
        self.download_btn.clicked.connect(lambda: self.download_requested.emit(self.info))
        self.delete_btn = None
        if info["is_user"]:
            self.delete_btn = QtWidgets.QToolButton()
            self.delete_btn.setText("×")
            self.delete_btn.setToolTip("Delete this data source")
            self.delete_btn.setAutoRaise(True)
            self.delete_btn.setCursor(Qt.ArrowCursor)
            self.delete_btn.setStyleSheet("QToolButton { color: #b9c2c8; font-size: 11pt; border: none; }"
                                          "QToolButton:hover { color: #a31b1b; background: #f6e9e9; }")
            self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.info))
            self.delete_btn.setVisible(False)

        # Compact single row: name, then badges and actions on the right.
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(name, 1)
        badges = header
        if info["key_names"]:
            if info["missing_keys"]:
                badge = _badge("Key needed", "key_missing")
                badge.setToolTip("Enter " + ", ".join(info["missing_keys"]) + " in the API Keys tab")
            else:
                badge = _badge("Key set", "key_ok")
            badges.addWidget(badge)
        if info["overrides_builtin"]:
            badges.addWidget(_badge("Customized", "custom"))
        elif info["is_user"]:
            badges.addWidget(_badge("Mine", "mine"))
        else:
            badges.addWidget(_badge("Built-in", "builtin"))
        header.addWidget(self.download_btn)
        if self.delete_btn:
            header.addWidget(self.delete_btn)

        text = QtWidgets.QVBoxLayout()
        text.setSpacing(1)
        text.addLayout(header)
        text.addWidget(desc)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 6, 6)
        layout.setSpacing(9)
        layout.addWidget(avatar, 0, Qt.AlignVCenter)
        layout.addLayout(text, 1)

    @staticmethod
    def _icon(svg):
        from qgis.PyQt.QtGui import QIcon
        return QIcon(_svg_pixmap(svg, 28))

    def enterEvent(self, event):
        if self.delete_btn:
            self.delete_btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.delete_btn:
            self.delete_btn.setVisible(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.opened.emit(self.info)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.opened.emit(self.info)
            return
        super().keyPressEvent(event)


def _render_handbook(text):
    """Handbook text as HTML: line breaks kept, `backtick` spans as code
    chips, URLs as links. Escaped first, so a handbook cannot inject markup."""
    out = []
    for line in str(text or "").splitlines():
        line = html.escape(line.strip())
        line = re.sub(r"`([^`]+)`", r"<code style='background:#eef3f6;'>\1</code>", line)
        line = re.sub(r"(https?://[^\s<]+)", r"<a href='\1'>\1</a>", line)
        out.append(line)
    return "<br>".join(out) or "&mdash;"


class DataSourceDetailDialog(QtWidgets.QDialog):
    """Details of one data source, with Edit / Download / Delete."""
    edit_requested = pyqtSignal(str)
    keys_requested = pyqtSignal(str)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        self.deleted = False
        color = card_color(info["name"] or info["id"])
        self.setWindowTitle(info["name"] or info["id"])
        self.resize(640, 620)

        avatar = QtWidgets.QLabel()
        avatar.setPixmap(_svg_pixmap(_DB_ICON_SVG, 40, background=color, radius=10))
        title = QtWidgets.QLabel(html.escape(info["name"] or info["id"]))
        title_font = title.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.35)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {color};")
        title.setWordWrap(True)
        origin = ("Your version of a built-in data source" if info["overrides_builtin"]
                  else "Your data source" if info["is_user"] else "Built-in data source")
        subtitle = QtWidgets.QLabel(f"{origin} &middot; ID: <code>{html.escape(info['id'])}</code>")
        subtitle.setStyleSheet("color: #74838c;")
        head_text = QtWidgets.QVBoxLayout()
        head_text.addWidget(title)
        head_text.addWidget(subtitle)
        head = QtWidgets.QHBoxLayout()
        head.addWidget(avatar, 0, Qt.AlignTop)
        head.addLayout(head_text, 1)

        body = QtWidgets.QVBoxLayout()
        body.addWidget(self._section("Description"))
        desc = QtWidgets.QLabel(html.escape(info["description"] or "—"))
        desc.setWordWrap(True)
        desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(desc)

        if info["website"]:
            body.addWidget(self._section("Website"))
            link = QtWidgets.QLabel(f"<a href='{html.escape(info['website'], quote=True)}'>"
                                    f"{html.escape(info['website'])}</a>")
            link.setOpenExternalLinks(True)
            body.addWidget(link)

        if info["key_names"]:
            body.addWidget(self._section("Required credentials"))
            chips = QtWidgets.QHBoxLayout()
            for name in info["key_names"]:
                missing = name in info["missing_keys"]
                chip = _badge(f"{name}: {'not set' if missing else 'set'}", "key_missing" if missing else "key_ok")
                chips.addWidget(chip)
            chips.addStretch(1)
            keys_btn = QtWidgets.QPushButton("Enter API keys...")
            keys_btn.clicked.connect(lambda: (self.keys_requested.emit(info["id"]), self.accept()))
            chips.addWidget(keys_btn)
            body.addLayout(chips)
            url = info["key_links"].get("website") or info["key_links"].get("signup_url")
            if url:
                signup = QtWidgets.QLabel(f"Get a key at: <a href='{html.escape(url, quote=True)}'>"
                                          f"{html.escape(url)}</a>")
                signup.setOpenExternalLinks(True)
                body.addWidget(signup)

        if info["caveats"]:
            body.addWidget(self._section("Caveats"))
            caveats = QtWidgets.QLabel(html.escape(info["caveats"]).replace("\n", "<br>"))
            caveats.setWordWrap(True)
            caveats.setStyleSheet("color: #9a6300;")
            body.addWidget(caveats)

        body.addWidget(self._section("Handbook"))
        handbook = QtWidgets.QTextBrowser()
        handbook.setOpenExternalLinks(True)
        handbook.setHtml(_render_handbook(info["handbook"]))
        body.addWidget(handbook, 2)

        if info["code_example"]:
            body.addWidget(self._section("Code example"))
            code = QtWidgets.QPlainTextEdit(info["code_example"])
            code.setReadOnly(True)
            code.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            mono = QFont("Consolas")
            mono.setStyleHint(QFont.Monospace)
            code.setFont(mono)
            body.addWidget(code, 2)

        buttons = QtWidgets.QHBoxLayout()
        edit_btn = QtWidgets.QPushButton("Edit in Handbook Studio")
        edit_btn.setToolTip("Editing a built-in data source saves your own version of it")
        edit_btn.clicked.connect(lambda: (self.edit_requested.emit(info["id"]), self.accept()))
        download_btn = QtWidgets.QPushButton("Download .toml")
        download_btn.clicked.connect(lambda: download_source(info, self))
        buttons.addWidget(edit_btn)
        buttons.addWidget(download_btn)
        if info["is_user"]:
            share_btn = QtWidgets.QPushButton("Share on GitHub...")
            share_btn.setToolTip("Contribute this data source to the plugin, so every user gets it")
            share_btn.clicked.connect(self._on_share)
            buttons.addWidget(share_btn)
            delete_btn = QtWidgets.QPushButton("Delete")
            delete_btn.setStyleSheet("QPushButton { color: #a31b1b; }")
            delete_btn.clicked.connect(self._on_delete)
            buttons.addWidget(delete_btn)
        buttons.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(head)
        layout.addLayout(body, 1)
        layout.addLayout(buttons)

    @staticmethod
    def _section(text):
        label = QtWidgets.QLabel(text.upper())
        font = label.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 0.85)
        label.setFont(font)
        label.setStyleSheet("color: #5b6b75; margin-top: 8px;")
        return label

    def _on_share(self):
        from .github_share import ShareOnGitHubDialog
        ShareOnGitHubDialog(self.info["id"], parent=self).exec_()

    def _on_delete(self):
        if delete_source(self.info, self):
            self.deleted = True
            self.accept()


def download_source(info, parent=None):
    """Save a copy of the source's handbook (.toml), re-importable in the studio."""
    target, _ = QtWidgets.QFileDialog.getSaveFileName(
        parent, "Download data source", f"{info['id']}.toml", "TOML Files (*.toml)")
    if not target:
        return False
    try:
        shutil.copyfile(info["path"], target)
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent, "Download failed", str(e))
        return False
    return True


def delete_source(info, parent=None):
    """Delete one of the user's own data sources (after confirmation)."""
    if not info["is_user"]:
        return False
    if info["overrides_builtin"]:
        question = (f"Delete your version of '{info['name']}'? The built-in version will be used again. "
                    "Your saved API keys for it are deleted too.")
    else:
        question = f"Delete the data source '{info['name']}'? Its saved API keys are deleted too."
    if QtWidgets.QMessageBox.question(parent, "Delete data source", question) != QtWidgets.QMessageBox.Yes:
        return False
    try:
        handbook_store.delete_user_handbook(info["id"])
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent, "Delete failed", str(e))
        return False
    return True


class DataSourcesPanel(QtWidgets.QWidget):
    """Search box + 'Add data source' + a responsive grid of source cards."""
    add_requested = pyqtSignal()
    edit_requested = pyqtSignal(str)
    keys_requested = pyqtSignal(str)
    sources_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._columns = 0
        self._empty_label = None

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search data sources...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        add_btn = QtWidgets.QPushButton("+ Add data source")
        add_btn.setToolTip("Create a handbook for a new data source, with AI or manually")
        add_btn.clicked.connect(self.add_requested.emit)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.search_edit, 1)
        top.addWidget(add_btn)

        self.count_label = QtWidgets.QLabel()
        self.count_label.setStyleSheet("color: #74838c;")

        self.grid_host = QtWidgets.QWidget()
        self.grid = QtWidgets.QGridLayout(self.grid_host)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(6)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setWidget(self.grid_host)
        self.scroll.viewport().installEventFilter(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self.count_label)
        layout.addWidget(self.scroll, 1)

        self.refresh()

    # ── Building ───────────────────────────────────────────────────────
    def refresh(self):
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        try:
            sources = handbook_store.list_sources()
        except Exception as e:
            sources = []
            self.count_label.setText(f"Could not read the data sources: {e}")
        for info in sources:
            card = DataSourceCard(info)
            card.opened.connect(self.show_details)
            card.download_requested.connect(lambda i: download_source(i, self))
            card.delete_requested.connect(self._delete)
            self._cards.append(card)
        self._columns = 0
        self._apply_filter()

    def _visible_cards(self):
        query = self.search_edit.text().strip().lower()
        return [c for c in self._cards
                if not query or query in f"{c.info['name']} {c.info['id']} {c.info['description']}".lower()]

    def _apply_filter(self):
        visible = self._visible_cards()
        total = len(self._cards)
        shown = f"{len(visible)} of {total}" if len(visible) != total else f"{total}"
        self.count_label.setText(f"{shown} data source{'s' if total != 1 else ''}")
        self._layout_cards(visible, force=True)

    def _layout_cards(self, visible=None, force=False):
        visible = self._visible_cards() if visible is None else visible
        columns = 1  # one card per row
        if columns == self._columns and not force:
            return
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        if self._empty_label is not None:
            self._empty_label.deleteLater()
            self._empty_label = None
        for card in self._cards:
            card.setVisible(False)
        for index, card in enumerate(visible):
            self.grid.addWidget(card, index // columns, index % columns)
            card.setVisible(True)
        for col in range(self.grid.columnCount()):
            self.grid.setColumnStretch(col, 1 if col < columns else 0)
        self.grid.setRowStretch(self.grid.rowCount(), 1)
        if not visible:
            empty = QtWidgets.QLabel("No data sources match your search." if self._cards
                                     else "No data sources yet. Add one so the agent can retrieve from it.")
            empty.setStyleSheet("color: #74838c; padding: 20px;")
            empty.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(empty, 0, 0, 1, columns)
            self._empty_label = empty

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._layout_cards()
        return super().eventFilter(obj, event)

    # ── Actions ────────────────────────────────────────────────────────
    def show_details(self, info):
        dialog = DataSourceDetailDialog(info, self)
        dialog.edit_requested.connect(self.edit_requested.emit)
        dialog.keys_requested.connect(self.keys_requested.emit)
        dialog.exec_()
        if dialog.deleted:
            self.refresh()
            self.sources_changed.emit()

    def _delete(self, info):
        if delete_source(info, self):
            self.refresh()
            self.sources_changed.emit()
