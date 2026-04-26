"""Main window — the QTabWidget host containing all six tabs."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QStatusBar,
    QTabWidget,
)

from ada_research.tabs.sprint1_market import Sprint1Tab
from ada_research.tabs.sprint2_sectors import Sprint2Tab
from ada_research.tabs.sprint3_analysts import Sprint3Tab
from ada_research.tabs.sprint4_screener import Sprint4Tab
from ada_research.tabs.stage1_sentiment import Stage1Tab
from ada_research.tabs.stage2_macro import Stage2Tab


class MainWindow(QMainWindow):
    """The Ada Research workbench."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ada Research")
        self.resize(1400, 900)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setMovable(False)
        self.tabs.setDocumentMode(True)

        self.tabs.addTab(Stage1Tab(),   "Stage 1 · Sentiment")
        self.tabs.addTab(Stage2Tab(),   "Stage 2 · Macro")
        self.tabs.addTab(Sprint1Tab(),  "Sprint 1 · Market")
        self.tabs.addTab(Sprint2Tab(),  "Sprint 2 · Sectors")
        self.tabs.addTab(Sprint3Tab(),  "Sprint 3 · Analysts")
        self.tabs.addTab(Sprint4Tab(),  "Sprint 4 · Screener")
        self.setCentralWidget(self.tabs)

        # Status bar
        status = QStatusBar()
        status.showMessage("Ready")
        self.setStatusBar(status)

        self._build_menu()

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menu.addMenu("&View")
        for i in range(self.tabs.count()):
            tab_name = self.tabs.tabText(i)
            action = QAction(tab_name, self)
            action.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            action.triggered.connect(lambda _, idx=i: self.tabs.setCurrentIndex(idx))
            view_menu.addAction(action)
