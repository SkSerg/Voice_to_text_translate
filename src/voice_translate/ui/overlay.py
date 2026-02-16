from PySide6.QtWidgets import QWidget, QVBoxLayout, QApplication, QFrame, QTextEdit, QSizeGrip, QMenu
from PySide6.QtCore import Qt, QTimer, QSize, QEvent
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor

from voice_translate.transcript_store import ts_store
from voice_translate.config import cfg

class DraggableTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(False)  # Allow text selection
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.drag_pos = None
        self.is_dragging_window = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if Ctrl is pressed - always drag window
            if event.modifiers() & Qt.ControlModifier:
                self.is_dragging_window = True
                self.drag_pos = event.globalPos() - self.window().frameGeometry().topLeft()
                event.accept()
                return
            
            # Check if clicking on text - allow selection
            cursor = self.cursorForPosition(event.pos())
            if not cursor.atEnd() or cursor.position() > 0:
                # There is text at this position, allow default selection behavior
                self.is_dragging_window = False
                super().mousePressEvent(event)
            else:
                # Clicking in empty area - drag window
                self.is_dragging_window = True
                self.drag_pos = event.globalPos() - self.window().frameGeometry().topLeft()
                event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            if self.is_dragging_window and self.drag_pos:
                # Dragging the window
                self.window().move(event.globalPos() - self.drag_pos)
                event.accept()
            else:
                # Allow text selection
                super().mouseMoveEvent(event)
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging_window = False
            self.drag_pos = None
        super().mouseReleaseEvent(event)
    
    def contextMenuEvent(self, event):
        """Show context menu on right click for copying text"""
        menu = QMenu(self)
        
        # Style the context menu to match the overlay theme
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(30, 30, 30, 240);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: rgba(255, 215, 0, 100);
            }
        """)
        
        # Add copy action
        copy_action = menu.addAction("Копировать выделенное (Ctrl+C)")
        copy_action.triggered.connect(self.copy)
        copy_action.setEnabled(self.textCursor().hasSelection())
        
        # Add select all action
        select_all_action = menu.addAction("Выделить всё (Ctrl+A)")
        select_all_action.triggered.connect(self.selectAll)
        
        # Add copy all action
        copy_all_action = menu.addAction("Копировать весь текст")
        copy_all_action.triggered.connect(self.copy_all_text)
        
        menu.exec(event.globalPos())
    
    def copy_all_text(self):
        """Copy all text to clipboard"""
        # Save current cursor position
        cursor = self.textCursor()
        old_position = cursor.position()
        
        # Select all and copy
        self.selectAll()
        self.copy()
        
        # Restore cursor position
        cursor.setPosition(old_position)
        self.setTextCursor(cursor)
            
    def wheelEvent(self, event):
        # Always accept wheel event to stop it from passing through to windows below
        super().wheelEvent(event)
        event.accept()

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        # Window flags
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # Layout
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0) # No margins so editor fills window
        self.setLayout(self.layout)
        
        # Style (Window transparency mostly for rounded corners)
        self.setStyleSheet("background-color: transparent;")
        
        # Text Area (Log)
        self.text_editor = DraggableTextEdit(self)
        self.text_editor.setFrameStyle(QFrame.NoFrame)
        
        # Apply the "Solid" background here to the Editor
        self.text_editor.setStyleSheet("""
            background-color: rgba(0, 0, 0, 245); 
            border-radius: 10px;
        """)
        self.text_editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded) # Show scrollbar if needed
        # Scrollbar styling
        self.text_editor.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical {
                border: none;
                background: rgba(0,0,0,50);
                width: 10px;
                margin: 5px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,100);
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Set font
        font = QFont("Arial", 20)
        self.text_editor.setFont(font)
        
        self.layout.addWidget(self.text_editor)
        
        # Resize Grip
        self.grip_layout = QVBoxLayout()
        self.grip_layout.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(30, 30)
        self.size_grip.setStyleSheet("""
            background-color: rgba(255, 255, 255, 50); 
            border-top-left-radius: 15px;
        """)
        self.size_grip.raise_()
        
        # Initial Position
        screen = QApplication.primaryScreen().geometry()
        width = 800
        height = 500 # Slightly taller
        x = (screen.width() - width) // 2
        y = screen.height() - height - 100
        self.setGeometry(x, y, width, height)
        
        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_content)
        self.timer.start(100) # 100ms
        
        self.last_html = ""

    def update_content(self):
        # Build HTML content
        html = ""
        
        # 1. History (Show larger context, e.g., last 50 segments)
        history_items = ts_store.get_latest(50)
        
        for item in history_items:
            # Original
            # Changed to White, added background
            html += f"<div style='color: #FFFFFF; font-size: 20px; margin-bottom: 2px; background-color: rgba(0,0,0,100); padding: 2px; border-radius: 3px;'>{item.segment.src_text}</div>"
            
            # Translation
            if item.translation:
                # Green-Gold for finished translation
                # Darker background (150 -> 200)
                html += f"<div style='color: #FFD700; font-size: 24px; font-weight: bold; margin-bottom: 20px; background-color: rgba(0,0,0,180); padding: 5px; border-radius: 5px;'>{item.translation.ru_text}</div>"
            else:
                if item.segment.lang != 'ru':
                    html += f"<div style='color: #888888; font-size: 16px; margin-bottom: 20px;'>...Wait...</div>"
                else:
                    html += "<div style='margin-bottom: 20px;'></div>"

        # 2. Live Text
        live_text = ts_store.live_stable + ts_store.live_unstable
        if live_text.strip():
             # Darker background (150 -> 230)
             html += f"<div style='color: #FFFFFF; font-size: 22px; font-style: italic; margin-top: 10px; background-color: rgba(20,20,20,230); padding: 5px; border-radius: 5px;'>{live_text}</div>"
             
        if html != self.last_html:
            self.text_editor.setHtml(html)
            self.last_html = html
            
            # Always scroll to bottom to show latest text
            self.text_editor.moveCursor(QTextCursor.End)
            self.text_editor.ensureCursorVisible()
            
    def resizeEvent(self, event):
        rect = self.rect()
        self.size_grip.move(rect.right() - 30, rect.bottom() - 30)
        super().resizeEvent(event)
