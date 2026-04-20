"""
SDS KHOJ - Safety Data Sheet Search 
--------------------------------------------
Author: Vignesh R, 2025

Description:
A PyQt5-based application to quickly search Safety Data Sheets (SDS) online
using DuckDuckGo search. Now uses the duckduckgo_search Python library instead
of fragile HTML scraping, so layout changes on DuckDuckGo do not break it.

THIS CODE IS WRITTEN BY VIGNESH R, with search + threading fixes integrated.
"""

import sys
import webbrowser
import threading
import time
import re
import html

from duckduckgo_search import DDGS  # <- New, stable search backend

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGraphicsDropShadowEffect, QComboBox, QMessageBox
)
from PyQt5.QtGui import QCursor, QColor, QIcon
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal

# ---------------- THEMES ---------------- #
THEMES = {
    "light": {
        "bg": "#FFFFFF",
        "card_bg": "#FFFFFF",
        "accent": "#1E88E5",
        "text": "#212121",
        "entry_bg": "#FFFFFF",
    },
    "dark": {
        "bg": "#121212",
        "card_bg": "#1E1E1E",
        "accent": "#4A90E2",
        "text": "#E0E0E0",
        "entry_bg": "#2A2A2A",
    },
}

# ---------------- CONSTANTS ---------------- #
USER_AGENT = "Mozilla/5.0 SDS-KHOJ"
LAST_SEARCH_TIME = 0

# ---------------- MULTILINGUAL SDS TERMS ---------------- #
SDS_TERMS = {
    "EN": ["SDS", "Safety Data Sheet", "MSDS"],
    "Arabic": ["ورقة بيانات السلامة"],
    "CN": ["安全数据表"],
    "Czech": ["Bezpečnostní list"],
    "DE": ["Sicherheitsdatenblatt"],
    "ES": ["Hoja de datos de seguridad"],
    "FR": ["Fiche de données de sécurité"],
    "IT": ["Scheda di sicurezza"],
    "JP": ["安全データシート"],
    "NL": ["Veiligheidsinformatieblad"],
    "PL": ["Karta charakterystyki"],
    "Portuguese": ["Ficha de dados de segurança"],
    "SE": ["Säkerhetsdatablad"],
    "Slovak": ["Bezpečnostný list"],
    "TR": ["Güvenlik Bilgi Formu"]
}

# ---------------- SEARCH HELPERS ---------------- #
def normalize_url(href: str) -> str:
    if not href:
        return href
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("www."):
        return "https://" + href
    return href


def single_ddg_search(query: str, max_results: int = 6, debug: bool = False):
    """
    Perform a single DuckDuckGo search using the duckduckgo_search library
    instead of scraping HTML. This makes the tool robust to layout changes.
    """
    results = []
    seen = set()

    try:
        # DDGS() handles all the HTTP, parsing and layout quirks internally.
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                url = r.get("href") or r.get("url")
                title = r.get("title") or url
                if not url:
                    continue
                url = normalize_url(url)
                if not url or url in seen or "duckduckgo.com" in url:
                    continue
                results.append({"title": title, "url": url})
                seen.add(url)
    except Exception as e:
        if debug:
            print(f"[single_ddg_search] Error: {e}")
        # If error, just return empty results; caller handles message.

    if not results:
        results.append({"title": "⚠️ No results found", "url": ""})

    return results


def multi_language_search(product: str, lang: str, max_results: int = 20):
    """
    Perform SDS searches in English + selected language terms.
    Uses the stable single_ddg_search() above.
    """
    local_terms = SDS_TERMS.get(lang, [])
    combined_terms = SDS_TERMS["EN"] + local_terms if lang and lang != "EN" else SDS_TERMS["EN"]
    all_results = []
    seen_urls = set()

    for term in combined_terms:
        q = f"{product} {term} PDF"
        results = single_ddg_search(q, max_results=5)
        for r in results:
            url = r.get("url")
            if url and url not in seen_urls:
                all_results.append(r)
                seen_urls.add(url)
        # Small delay to be polite
        time.sleep(0.4)

    if not all_results:
        raise ValueError("No SDS results found.")
    return all_results[:max_results]


def is_safe_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    return True


# ---------------- MAIN APP ---------------- #
class SDSKhoj(QWidget):
    # Signals to safely communicate from worker thread to UI thread
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        # Window properties
        self.setWindowIcon(QIcon())
        self.setWindowTitle("SDS KHOJ")
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        self.setWindowOpacity(1.0)
        self.setMinimumSize(960, 600)

        # Theme and state
        self.theme_name = "light"
        self.colors = THEMES[self.theme_name]
        self.logo_clicks = 0
        self.credit_hidden = "✨ Developed by Amartya Thakur @2025 ✨"

        # Build UI
        self.setup_ui()
        self.apply_theme()

        # Connect signals
        self.results_ready.connect(self._on_results_ready)
        self.error_occurred.connect(self._on_error)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Theme toggle button
        self.btn_theme = QPushButton("🌙")
        self.btn_theme.setFixedSize(46, 32)
        self.btn_theme.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_theme.clicked.connect(self.animated_toggle_theme)

        # ---------- Card container ----------
        self.card = QWidget()
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        # Softer shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(14)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.card.setGraphicsEffect(shadow)

        # ---------- Search row ----------
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        search_layout.addWidget(self.btn_theme)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Enter the product name...")
        self.entry.returnPressed.connect(self.start_search)
        search_layout.addWidget(self.entry, stretch=3)

        self.lang_dropdown = QComboBox()
        self.lang_dropdown.addItems([
            "EN - Default_All", "Arabic", "CN", "Czech", "DE", "ES", "FR",
            "IT", "JP", "NL", "PL", "Portuguese", "SE", "Slovak", "TR"
        ])
        search_layout.addWidget(self.lang_dropdown, stretch=1)

        self.btn_search = QPushButton("🔍 Search")
        self.btn_search.clicked.connect(self.start_search)
        search_layout.addWidget(self.btn_search)

        self.btn_openall = QPushButton("🌐 Open All")
        self.btn_openall.clicked.connect(self.open_all)
        search_layout.addWidget(self.btn_openall)

        self.btn_clear = QPushButton("❌ Clear")
        self.btn_clear.clicked.connect(self.clear_all)
        search_layout.addWidget(self.btn_clear)

        card_layout.addLayout(search_layout)

        # ---------- Results table ----------
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Result Title", "URL"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.open_selected)
        card_layout.addWidget(self.table)

        # Status label
        self.status_lbl = QLabel("Ready")
        card_layout.addWidget(self.status_lbl)

        main_layout.addWidget(self.card)

    # ---------------- THEME ---------------- #
    def apply_theme(self):
        c = self.colors
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {c['bg']};
                color: {c['text']};
                font-family: 'Segoe UI', sans-serif;
            }}
            QLineEdit {{
                background-color: {c['entry_bg']};
                color: {c['text']};
                border-radius: 12px;
                padding: 8px;
            }}
            QPushButton {{
                background-color: {c['accent']};
                color: white;
                border-radius: 12px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
            }}
            QComboBox {{
                background-color: {c['entry_bg']};
                color: {c['text']};
                border-radius: 10px;
                padding: 6px;
            }}
            QHeaderView::section {{
                background-color: {c['accent']};
                color: #fff;
                padding: 6px;
                border: none;
            }}
        """)
        self.btn_theme.setText("🌞" if self.theme_name == "dark" else "🌙")
        self.setWindowOpacity(1.0)

    def animated_toggle_theme(self):
        btn = self.btn_theme
        start_rect = btn.geometry()
        shrink_rect = QRect(
            start_rect.x() + 2,
            start_rect.y() + 2,
            max(16, start_rect.width() - 4),
            max(12, start_rect.height() - 4),
        )

        anim = QPropertyAnimation(btn, b"geometry", self)
        anim.setDuration(120)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(start_rect)
        anim.setKeyValueAt(0.5, shrink_rect)
        anim.setEndValue(start_rect)
        anim.start()

        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.colors = THEMES[self.theme_name]
        self.apply_theme()

    # ---------------- SEARCH LOGIC ---------------- #
    def start_search(self):
        global LAST_SEARCH_TIME
        now = time.time()
        if now - LAST_SEARCH_TIME < 1:
            self.status_lbl.setText("Please wait before searching again...")
            return
        LAST_SEARCH_TIME = now

        query = self.entry.text().strip()
        if not query:
            self.status_lbl.setText("Enter product or brand to search.")
            return
        if len(query) > 100:
            self.status_lbl.setText("Query too long. Please shorten your search.")
            return

        query = re.sub(r'[<>\'";]', '', query)
        lang = self.lang_dropdown.currentText().split(" - ")[0]
        self.status_lbl.setText(f"Searching SDS in {lang} ......")

        # Background thread for search
        t = threading.Thread(target=self._do_search, args=(query, lang), daemon=True)
        t.start()

    def _do_search(self, query, lang):
        try:
            results = multi_language_search(query, lang)
            self.results_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(f"Error: {str(e)}")

    # Slots for signals
    def _on_results_ready(self, results):
        self.table.setRowCount(0)
        for r in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            title_item = QTableWidgetItem(html.escape(r["title"]))
            url_item = QTableWidgetItem(html.escape(r["url"]))
            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, url_item)
        self.status_lbl.setText(f"Found {len(results)} results.")

    def _on_error(self, message: str):
        self.table.setRowCount(0)
        self.status_lbl.setText(message)

    # ---------------- ACTIONS ---------------- #
    def open_selected(self, row, col):
        url_item = self.table.item(row, 1)
        if url_item:
            url = url_item.text()
            if is_safe_url(url):
                webbrowser.open(url)
                self.status_lbl.setText("Opened link.")
            else:
                QMessageBox.warning(self, "Security Alert", "Potentially unsafe URL blocked.")

    def open_all(self):
        total_links = self.table.rowCount()
        if total_links == 0:
            self.status_lbl.setText("No links to open.")
            return

        if total_links > 5:
            confirm = QMessageBox.question(
                self,
                "Confirm Open All",
                f"Are you sure you want to open {total_links} links?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

        max_links = min(total_links, 10)
        links_opened = 0
        for row in range(max_links):
            url_item = self.table.item(row, 1)
            if url_item:
                url = url_item.text()
                if is_safe_url(url):
                    webbrowser.open(url)
                    time.sleep(0.3)
                    links_opened += 1

        if total_links > max_links:
            self.status_lbl.setText(f"Opened first {links_opened} of {total_links} links (limit reached).")
        else:
            self.status_lbl.setText(f"Opened {links_opened} links.")

    def clear_all(self):
        self.entry.clear()
        self.table.setRowCount(0)
        self.lang_dropdown.setCurrentIndex(0)
        self.status_lbl.setText("Cleared search.")


# ---------------- RUN APP ---------------- #
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SDSKhoj()
    window.show()
    sys.exit(app.exec_())
