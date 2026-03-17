"""AI Design Review panel — DFM analysis, design scoring & recommendations."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QFrame, QProgressBar, QScrollArea, QGroupBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from src.pcb.generator import Board
from src.pcb.dfm import DFMEngine, DFMIssue, DFMCategory, DFMSeverity, compute_dfm_score
from src.gui.i18n import tr
from src.gui.theme import tc, ThemeManager


# =====================================================================
# Severity styling
# =====================================================================

_SEV_ICONS = {
    DFMSeverity.CRITICAL: "🔴",
    DFMSeverity.WARNING: "🟡",
    DFMSeverity.INFO: "🔵",
}

_SEV_COLORS = {
    DFMSeverity.CRITICAL: QColor("#f85149"),
    DFMSeverity.WARNING: QColor("#d29922"),
    DFMSeverity.INFO: QColor("#58a6ff"),
}

_CAT_ICONS = {
    DFMCategory.MANUFACTURING: "🏭",
    DFMCategory.THERMAL: "🌡",
    DFMCategory.ELECTRICAL: "⚡",
    DFMCategory.ASSEMBLY: "🔧",
    DFMCategory.SIGNAL_INTEGRITY: "📡",
}


class DesignReviewPanel(QWidget):
    """Panel showing DFM analysis results, design score, and recommendations."""

    component_highlight = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Board | None = None
        self._issues: list[DFMIssue] = []
        self._build_ui()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # ── Header ──
        header = QHBoxLayout()
        self._title = QLabel(tr("review_title"))
        self._title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        header.addWidget(self._title)
        header.addStretch()

        self._btn_run = QPushButton(tr("review_run"))
        self._btn_run.clicked.connect(self._on_run)
        header.addWidget(self._btn_run)
        layout.addLayout(header)

        # ── Score card ──
        self._score_frame = QFrame()
        score_layout = QHBoxLayout(self._score_frame)
        score_layout.setContentsMargins(12, 8, 12, 8)

        # Score number
        self._score_label = QLabel("—")
        self._score_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self._score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_label.setMinimumWidth(70)
        score_layout.addWidget(self._score_label)

        # Score details
        score_detail = QVBoxLayout()
        self._score_title = QLabel(tr("review_score_title"))
        self._score_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        score_detail.addWidget(self._score_title)

        self._score_bar = QProgressBar()
        self._score_bar.setRange(0, 100)
        self._score_bar.setValue(0)
        self._score_bar.setTextVisible(False)
        self._score_bar.setFixedHeight(8)
        score_detail.addWidget(self._score_bar)

        self._score_summary = QLabel("")
        score_detail.addWidget(self._score_summary)

        score_layout.addLayout(score_detail, 1)
        layout.addWidget(self._score_frame)

        # ── Category summary ──
        self._cat_frame = QFrame()
        cat_layout = QHBoxLayout(self._cat_frame)
        cat_layout.setContentsMargins(8, 6, 8, 6)
        cat_layout.setSpacing(12)

        self._cat_labels: dict[DFMCategory, QLabel] = {}
        for cat in DFMCategory:
            icon = _CAT_ICONS.get(cat, "")
            lbl = QLabel(f"{icon} 0")
            lbl.setToolTip(cat.value.replace("_", " ").title())
            cat_layout.addWidget(lbl)
            self._cat_labels[cat] = lbl

        cat_layout.addStretch()
        layout.addWidget(self._cat_frame)

        # ── Issues tree ──
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels([tr("review_col_issue"), tr("review_col_recommendation")])
        self._tree.setColumnWidth(0, 400)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree, 1)

        # ── No-board placeholder ──
        self._placeholder = QLabel(tr("review_no_board"))
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder)

        self._apply_theme()
        self._set_has_results(False)

    def _set_has_results(self, has: bool):
        self._score_frame.setVisible(has)
        self._cat_frame.setVisible(has)
        self._tree.setVisible(has)
        self._placeholder.setVisible(not has)

    # ==================================================================
    # Public API
    # ==================================================================

    def load_board(self, board: Board | None):
        """Set the board and auto-run DFM analysis."""
        self._board = board
        if board:
            self._run_analysis()
        else:
            self._issues = []
            self._tree.clear()
            self._score_label.setText("—")
            self._score_bar.setValue(0)
            self._score_summary.setText("")
            self._set_has_results(False)

    def _on_run(self):
        if self._board:
            self._run_analysis()

    def _run_analysis(self):
        if not self._board:
            return

        engine = DFMEngine(self._board)
        self._issues = engine.run_all()
        score = compute_dfm_score(self._issues)
        self._update_display(score)

    # ==================================================================
    # Display
    # ==================================================================

    def _update_display(self, score: int):
        self._set_has_results(True)

        # Score
        self._score_label.setText(str(score))
        self._score_bar.setValue(score)

        if score >= 90:
            color = "#3fb950"
            grade = tr("review_grade_excellent")
        elif score >= 70:
            color = "#d29922"
            grade = tr("review_grade_good")
        elif score >= 50:
            color = "#db6d28"
            grade = tr("review_grade_fair")
        else:
            color = "#f85149"
            grade = tr("review_grade_poor")

        self._score_label.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: bold;")
        c = tc()
        self._score_bar.setStyleSheet(
            f"QProgressBar {{ background: {c.border_light}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
        )

        critical = sum(1 for i in self._issues if i.severity == DFMSeverity.CRITICAL)
        warning = sum(1 for i in self._issues if i.severity == DFMSeverity.WARNING)
        info = sum(1 for i in self._issues if i.severity == DFMSeverity.INFO)

        self._score_summary.setText(
            tr("review_summary", grade=grade, critical=critical,
               warnings=warning, info=info)
        )

        # Category counts
        cat_counts: dict[DFMCategory, int] = {c: 0 for c in DFMCategory}
        for issue in self._issues:
            cat_counts[issue.category] += 1
        for cat, lbl in self._cat_labels.items():
            icon = _CAT_ICONS.get(cat, "")
            count = cat_counts[cat]
            lbl.setText(f"{icon} {count}")
            if count > 0:
                lbl.setStyleSheet(f"color: {tc().text}; font-size: 11px; font-weight: bold;")
            else:
                lbl.setStyleSheet(f"color: {tc().text_dim}; font-size: 11px;")

        # Issues tree
        self._tree.clear()

        # Group by category
        grouped: dict[DFMCategory, list[DFMIssue]] = {c: [] for c in DFMCategory}
        for issue in self._issues:
            grouped[issue.category].append(issue)

        idx = 0
        for cat in DFMCategory:
            cat_issues = grouped[cat]
            if not cat_issues:
                continue

            icon = _CAT_ICONS.get(cat, "")
            cat_item = QTreeWidgetItem([
                f"{icon} {cat.value.replace('_', ' ').title()} ({len(cat_issues)})", ""
            ])
            cat_item.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            cat_item.setForeground(0, QColor(tc().text))
            self._tree.addTopLevelItem(cat_item)

            for issue in cat_issues:
                sev_icon = _SEV_ICONS.get(issue.severity, "")
                text = f"{sev_icon} [{issue.code}] {issue.title}: {issue.description}"
                rec = issue.recommendation or ""
                child = QTreeWidgetItem([text, f"💡 {rec}" if rec else ""])
                child.setForeground(0, _SEV_COLORS.get(issue.severity, QColor("#e6edf3")))
                child.setForeground(1, QColor(tc().text_dim))
                child.setData(0, Qt.ItemDataRole.UserRole, idx)
                cat_item.addChild(child)
                idx += 1

            cat_item.setExpanded(True)

        if not self._issues:
            self._score_summary.setText(tr("review_all_pass"))

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is not None and 0 <= idx < len(self._issues):
            issue = self._issues[idx]
            if issue.refs:
                self.component_highlight.emit(issue.refs[0])

    def _apply_theme(self):
        c = tc()
        self._title.setStyleSheet(f"color: {c.text};")
        self._btn_run.setStyleSheet(
            f"QPushButton {{ background: {c.accent}; color: white; border: none; "
            f"border-radius: 4px; padding: 4px 14px; font-size: 11px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {c.accent_hover}; }}"
        )
        self._score_frame.setStyleSheet(
            f"QFrame {{ background: {c.bg_secondary}; border: 1px solid {c.border}; "
            f"border-radius: 6px; padding: 8px; }}"
        )
        self._score_title.setStyleSheet(f"color: {c.text};")
        self._score_bar.setStyleSheet(
            f"QProgressBar {{ background: {c.border_light}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {c.success}; border-radius: 4px; }}"
        )
        self._score_summary.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")
        self._cat_frame.setStyleSheet(
            f"QFrame {{ background: {c.bg}; border: 1px solid {c.border}; "
            f"border-radius: 4px; }}"
        )
        for lbl in self._cat_labels.values():
            lbl.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {c.bg}; border: 1px solid {c.border}; "
            f"border-radius: 4px; color: {c.text}; font-size: 11px; "
            f"alternate-background-color: {c.bg_secondary}; }}"
            f"QTreeWidget::item {{ padding: 4px 6px; }}"
            f"QTreeWidget::item:hover {{ background: {c.hover_bg}; }}"
            f"QTreeWidget::item:selected {{ background: {c.selected_bg}; }}"
            f"QHeaderView::section {{ background: {c.bg_secondary}; color: {c.text_dim}; "
            f"border: 1px solid {c.border}; padding: 4px; font-size: 11px; }}"
        )
        self._placeholder.setStyleSheet(f"color: {c.text_dim}; font-size: 12px;")

    def retranslate(self):
        self._title.setText(tr("review_title"))
        self._btn_run.setText(tr("review_run"))
        self._score_title.setText(tr("review_score_title"))
        self._placeholder.setText(tr("review_no_board"))
        self._tree.setHeaderLabels([tr("review_col_issue"), tr("review_col_recommendation")])
        if self._board:
            self._run_analysis()
