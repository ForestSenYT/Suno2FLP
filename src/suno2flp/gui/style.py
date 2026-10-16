"""Studio workbench tokens; system fonts, no downloaded or bundled assets."""

STYLE = """
QWidget { color: #152C42; font-size: 14px; }
QMainWindow, QWidget#Canvas { background: #E7EBF0; }
QFrame#Rail { background: #183549; }
QFrame#Rail QLabel { color: #FFFFFF; }
QLabel#Brand { font-size: 25px; font-weight: 600; }
QLabel#Title { font-size: 26px; font-weight: 600; }
QLabel#Subtitle { font-size: 18px; font-weight: 600; }
QLabel#Muted { color: #526578; font-size: 12px; }
QLabel#Status { color: #8C5B14; font-size: 20px; font-weight: 600; }
QLabel#Notice { background: #DDE9EF; padding: 10px; border-radius: 4px; }
QLineEdit, QPlainTextEdit { background: #FFFFFF; border: 1px solid #ACBAC6;
    padding: 8px; border-radius: 4px; selection-background-color: #176C89; }
QPushButton, QToolButton { background: #FFFFFF; border: 1px solid #8DA2B3;
    border-radius: 4px; padding: 8px 12px; }
QPushButton#Primary { background: #176C89; color: #FFFFFF; border-color: #176C89; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus { border: 2px solid #176C89; }
QPushButton:disabled, QToolButton:disabled { color: #6E7D89; background: #DCE2E7; }
QListWidget { background: #183549; border: none; color: #FFFFFF; }
QListWidget::item { padding: 12px 5px; border-bottom: 1px solid #35536A; }
QListWidget::item:selected { background: #2D627B; }
QTableWidget { background: #FFFFFF; border: none; gridline-color: #DCE2E7; }
QHeaderView::section { background: #D5DFE7; border: none; padding: 5px; }
QProgressBar { background: #D5DFE7; border: none; max-height: 4px; }
QProgressBar::chunk { background: #176C89; }
"""
