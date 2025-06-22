#!/usr/bin/env python3
"""
Simple macOS Voice Control Assistant - Apple Style
A Python application that scans UI elements and shows Apple Voice Control style overlays.
"""

import sys
import time
from typing import List, Optional, Dict
from dataclasses import dataclass

# PyQt6 imports
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QRect, QRectF, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QPainter, QPainterPath, QColor, QPen

# PyObjC imports
from Foundation import NSWorkspace
from AppKit import NSScreen
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementPerformAction,
    AXValueGetValue,
    AXValueGetType,
    kAXValueCGPointType,
    kAXValueCGSizeType,
    kAXPressAction
)

# Expanded interactive roles to catch more elements
INTERACTIVE_ROLES = {
    'AXButton', 'AXTextField', 'AXLink', 'AXMenuItem', 'AXCheckBox', 
    'AXRadioButton', 'AXSlider', 'AXPopUpButton', 'AXTabButton',
    'AXStaticText', 'AXImage', 'AXGroup', 'AXCell', 'AXRow', 'AXColumn'
}

@dataclass
class UIElement:
    number: int
    role: str
    x: float
    y: float
    width: float
    height: float
    ax_element: object = None
    title: str = ""


class AppleBadge(QLabel):
    """Custom badge widget that mimics Apple's Voice Control style with color coding."""
    
    def __init__(self, text, element_center_x, element_center_y, element_role, parent=None):
        super().__init__(parent)
        self.badge_text = text
        self.element_center_x = element_center_x
        self.element_center_y = element_center_y
        self.element_role = element_role
        self.setup_widget()
        
    def get_color_for_role(self, role):
        """Get color scheme based on element role/type."""
        # Define color schemes for different element types
        color_schemes = {
            # Buttons - Blue theme
            'AXButton': {'bg': QColor(0, 122, 255, 180), 'border': QColor(255, 255, 255, 80)},
            'AXMenuButton': {'bg': QColor(0, 122, 255, 160), 'border': QColor(255, 255, 255, 80)},
            'AXPopUpButton': {'bg': QColor(0, 122, 255, 160), 'border': QColor(255, 255, 255, 80)},
            
            # Text inputs - Green theme  
            'AXTextField': {'bg': QColor(52, 199, 89, 180), 'border': QColor(255, 255, 255, 80)},
            'AXTextArea': {'bg': QColor(52, 199, 89, 160), 'border': QColor(255, 255, 255, 80)},
            'AXStaticText': {'bg': QColor(52, 199, 89, 140), 'border': QColor(255, 255, 255, 60)},
            
            # Links and navigation - Purple theme
            'AXLink': {'bg': QColor(175, 82, 222, 180), 'border': QColor(255, 255, 255, 80)},
            'AXMenuItem': {'bg': QColor(175, 82, 222, 160), 'border': QColor(255, 255, 255, 80)},
            'AXTabButton': {'bg': QColor(175, 82, 222, 160), 'border': QColor(255, 255, 255, 80)},
            
            # Form controls - Orange theme
            'AXCheckBox': {'bg': QColor(255, 149, 0, 180), 'border': QColor(255, 255, 255, 80)},
            'AXRadioButton': {'bg': QColor(255, 149, 0, 180), 'border': QColor(255, 255, 255, 80)},
            'AXSlider': {'bg': QColor(255, 149, 0, 160), 'border': QColor(255, 255, 255, 80)},
            
            # Data elements - Red theme
            'AXCell': {'bg': QColor(255, 59, 48, 160), 'border': QColor(255, 255, 255, 80)},
            'AXRow': {'bg': QColor(255, 59, 48, 140), 'border': QColor(255, 255, 255, 60)},
            'AXColumn': {'bg': QColor(255, 59, 48, 120), 'border': QColor(255, 255, 255, 60)},
            
            # Containers - Yellow theme
            'AXGroup': {'bg': QColor(255, 204, 0, 140), 'border': QColor(255, 255, 255, 60)},
            'AXScrollArea': {'bg': QColor(255, 204, 0, 120), 'border': QColor(255, 255, 255, 60)},
            
            # Media - Teal theme
            'AXImage': {'bg': QColor(90, 200, 250, 160), 'border': QColor(255, 255, 255, 80)},
            
            # Default - Dark theme
            'default': {'bg': QColor(0, 0, 0, 180), 'border': QColor(255, 255, 255, 80)}
        }
        
        return color_schemes.get(role, color_schemes['default'])
        
    def setup_widget(self):
        # Calculate size based on text length
        font = QFont("SF Pro Text", 11, QFont.Weight.Medium)
        if not font.exactMatch():
            font = QFont("Helvetica Neue", 11, QFont.Weight.Medium)
        if not font.exactMatch():
            font = QFont("Arial", 11, QFont.Weight.Bold)
        
        self.setFont(font)
        
        # Dynamic sizing based on text length
        text_width = len(self.badge_text) * 8 + 8
        badge_width = max(24, text_width)
        badge_height = 20
        
        self.setFixedSize(badge_width + 16, badge_height + 16)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get colors for this element type
        colors = self.get_color_for_role(self.element_role)
        bg_color = colors['bg']
        border_color = colors['border']
        text_color = QColor(255, 255, 255, 255)  # Always white text
        
        # Calculate tail direction toward the element
        badge_center_x = self.width() / 2
        badge_center_y = self.height() / 2
        
        # Get element position relative to badge position
        badge_screen_pos = self.mapToGlobal(self.rect().center())
        
        # Calculate direction vector from badge to element
        dx = self.element_center_x - badge_screen_pos.x()
        dy = self.element_center_y - badge_screen_pos.y()
        
        # Normalize and scale for tail
        import math
        distance = math.sqrt(dx*dx + dy*dy)
        if distance > 0:
            tail_length = 6
            tail_dx = (dx / distance) * tail_length
            tail_dy = (dy / distance) * tail_length
        else:
            tail_dx, tail_dy = 4, 4
        
        # Badge dimensions
        badge_width = self.width() - 16
        badge_height = self.height() - 16
        tail_size = 3
        
        # Create rounded rectangle path
        path = QPainterPath()
        
        # Main rounded rectangle (centered)
        main_rect = QRectF(8, 8, badge_width - 8, badge_height - 8)
        path.addRoundedRect(main_rect, 6, 6)
        
        # Add pointer tail pointing toward element
        tail_start_x = main_rect.center().x()
        tail_start_y = main_rect.center().y()
        
        # Find the point on the rectangle edge closest to the element direction
        if abs(tail_dx) > abs(tail_dy):
            # Horizontal direction dominant
            if tail_dx > 0:  # Point right
                tail_start_x = main_rect.right()
                tail_start_y = main_rect.center().y()
            else:  # Point left
                tail_start_x = main_rect.left()
                tail_start_y = main_rect.center().y()
        else:
            # Vertical direction dominant
            if tail_dy > 0:  # Point down
                tail_start_x = main_rect.center().x()
                tail_start_y = main_rect.bottom()
            else:  # Point up
                tail_start_x = main_rect.center().x()
                tail_start_y = main_rect.top()
        
        # Create tail triangle pointing toward element
        tail_path = QPainterPath()
        tail_path.moveTo(tail_start_x, tail_start_y)
        tail_path.lineTo(tail_start_x + tail_dx, tail_start_y + tail_dy)
        
        # Create perpendicular points for triangle base
        perp_x = -tail_dy * 0.3
        perp_y = tail_dx * 0.3
        
        tail_path.lineTo(tail_start_x + perp_x, tail_start_y + perp_y)
        tail_path.lineTo(tail_start_x - perp_x, tail_start_y - perp_y)
        tail_path.closeSubpath()
        
        # Combine main rectangle and tail
        path = path.united(tail_path)
        
        # Draw the badge with role-specific colors
        painter.fillPath(path, bg_color)
        
        # Draw border
        painter.setPen(QPen(border_color, 0.5))
        painter.drawPath(path)
        
        # Draw text
        painter.setPen(text_color)
        painter.setFont(self.font())
        
        # Center text in the main rectangle
        painter.drawText(main_rect, Qt.AlignmentFlag.AlignCenter, self.badge_text)


class NumberInput:
    """Handles multi-digit number input."""
    
    def __init__(self, overlay):
        self.overlay = overlay
        self.current_input = ""
        self.input_timer = QTimer()
        self.input_timer.timeout.connect(self.process_input)
        self.input_timer.setSingleShot(True)
        
    def add_digit(self, digit):
        """Add a digit to current input."""
        print(f"🔢 Digit pressed: {digit}")  # Debug: confirm input is received
        self.current_input += str(digit)
        print(f"📝 Current input: {self.current_input}")
        
        # Reset timer - wait for more input
        self.input_timer.stop()
        
        # Check if this could be a prefix of a larger number
        if self.has_possible_longer_matches():
            # Wait for more input - start timer
            self.input_timer.start(1000)  # 1 second timeout
            print(f"⏳ Waiting for more digits (possible longer matches exist)...")
        else:
            # No longer matches possible, process immediately if we have a match
            if self.is_complete_match():
                print(f"🎯 No longer matches possible, processing immediately")
                self.process_input()
            else:
                # Start timer anyway in case user wants to continue
                self.input_timer.start(1000)
                print(f"⏳ Starting timer for non-matching input")
    
    def has_possible_longer_matches(self):
        """Check if current input could be a prefix of a longer number."""
        if not self.current_input:
            return False
        
        current_num = self.current_input
        
        # Check if any element numbers start with our current input
        for element in self.overlay.elements:
            element_str = str(element.number)
            if element_str.startswith(current_num) and len(element_str) > len(current_num):
                return True
        return False
    
    def is_complete_match(self):
        """Check if current input exactly matches an element number."""
        if not self.current_input:
            return False
        try:
            num = int(self.current_input)
            # Check if this exact number exists
            for element in self.overlay.elements:
                if element.number == num:
                    return True
            return False
        except ValueError:
            return False
    
    def process_input(self):
        """Process the accumulated input."""
        if self.current_input:
            try:
                number = int(self.current_input)
                print(f"Processing input: {self.current_input} -> Element {number}")
                self.overlay.activate_element(number)
            except ValueError:
                print(f"Invalid input: {self.current_input}")
            finally:
                self.current_input = ""
    
    def clear_input(self):
        """Clear current input."""
        self.current_input = ""
        self.input_timer.stop()


class SimpleScanner:
    def __init__(self):
        self.element_counter = 1
        self.target_app_pid = None  # Remember the target app
        self.target_app_name = None

    def get_frontmost_app(self):
        """Get frontmost application info."""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            app = workspace.frontmostApplication()
            if app:
                return {
                    'pid': app.processIdentifier(),
                    'name': app.localizedName() or 'Unknown'
                }
        except Exception as e:
            print(f"Error getting app: {e}")
        return None

    def set_target_app(self, app_info):
        """Set the target application to scan."""
        if app_info:
            self.target_app_pid = app_info['pid']
            self.target_app_name = app_info['name']
            print(f"🎯 Target app set: {self.target_app_name} (PID: {self.target_app_pid})")

    def get_target_app_info(self):
        """Get the stored target app info."""
        if self.target_app_pid and self.target_app_name:
            return {
                'pid': self.target_app_pid,
                'name': self.target_app_name
            }
        return None

    def focus_target_app(self):
        """Bring target app to front."""
        try:
            if self.target_app_pid:
                workspace = NSWorkspace.sharedWorkspace()
                # Get all running apps
                running_apps = workspace.runningApplications()
                for app in running_apps:
                    if app.processIdentifier() == self.target_app_pid:
                        success = app.activateWithOptions_(0)  # Bring to front
                        if success:
                            print(f"✅ Focused back to {self.target_app_name}")
                            return True
                        else:
                            print(f"⚠️ Failed to focus {self.target_app_name}")
                            return False
                print(f"⚠️ Target app {self.target_app_name} not found in running apps")
        except Exception as e:
            print(f"❌ Error focusing target app: {e}")
        return False

    def test_permissions(self):
        """Test accessibility permissions."""
        try:
            app_info = self.get_frontmost_app()
            if not app_info:
                return False
            
            app_ref = AXUIElementCreateApplication(app_info['pid'])
            _, role = AXUIElementCopyAttributeValue(app_ref, 'AXRole', None)
            
            if role:
                print(f"✅ Accessibility OK - {app_info['name']} ({role})")
                return True
            else:
                print("❌ No accessibility access")
                return False
        except Exception as e:
            print(f"❌ Permission test failed: {e}")
            return False

    def get_element_geometry(self, element):
        """Get element position and size."""
        try:
            _, pos_ref = AXUIElementCopyAttributeValue(element, "AXPosition", None)
            _, size_ref = AXUIElementCopyAttributeValue(element, "AXSize", None)

            if not (pos_ref and size_ref):
                return None

            pos_ok, point = AXValueGetValue(pos_ref, kAXValueCGPointType, None)
            size_ok, size = AXValueGetValue(size_ref, kAXValueCGSizeType, None)

            if pos_ok and size_ok and size.width > 5 and size.height > 5:
                return {
                    'x': float(point.x),
                    'y': float(point.y),
                    'w': float(size.width),
                    'h': float(size.height)
                }
        except Exception as e:
            print(f"Geometry error: {e}")
        return None

    def scan_children(self, element, depth=0, max_depth=8):
        """Scan element children recursively."""
        if depth > max_depth:
            return []

        elements = []
        
        try:
            # Get element info
            _, role = AXUIElementCopyAttributeValue(element, 'AXRole', None)
            _, title = AXUIElementCopyAttributeValue(element, 'AXTitle', None)
            
            # Debug: Print ALL elements we encounter
            indent = "  " * depth
            print(f"{indent}Element: {role} - '{title or 'No title'}'")
            
            # Check if this element is interactive
            if role in INTERACTIVE_ROLES:
                print(f"{indent}  → Interactive role found!")
                geom = self.get_element_geometry(element)
                if geom:
                    print(f"{indent}  → Has geometry: {geom}")
                    ui_element = UIElement(
                        number=self.element_counter,
                        role=role,
                        x=geom['x'],
                        y=geom['y'],
                        width=geom['w'],
                        height=geom['h'],
                        ax_element=element,
                        title=title or ""
                    )
                    elements.append(ui_element)
                    self.element_counter += 1
                    print(f"{indent}  ✅ ADDED: {role} #{self.element_counter-1}")
                else:
                    print(f"{indent}  ❌ No geometry")
            elif role:
                print(f"{indent}  → Non-interactive: {role}")

            # Scan children
            _, children = AXUIElementCopyAttributeValue(element, 'AXChildren', None)
            if children:
                print(f"{indent}  Children: {len(children)}")
                for child in children:
                    elements.extend(self.scan_children(child, depth + 1, max_depth))
            else:
                print(f"{indent}  No children")
                    
        except Exception as e:
            print(f"  Error scanning element: {e}")
            
        return elements

    def scan_app(self, use_target_app=False):
        """Scan the frontmost application or the stored target app."""
        if use_target_app and self.target_app_pid:
            # Use the stored target app
            app_info = self.get_target_app_info()
            print(f"Scanning target app: {app_info['name']}")
        else:
            # Get current frontmost app and set it as target
            app_info = self.get_frontmost_app()
            if app_info and not self.target_app_pid:
                self.set_target_app(app_info)
        
        if not app_info:
            return []

        print(f"Scanning: {app_info['name']}")
        
        try:
            app_ref = AXUIElementCreateApplication(app_info['pid'])
            
            # Try to get main window and its position
            try:
                _, main_window = AXUIElementCopyAttributeValue(app_ref, 'AXMainWindow', None)
                if main_window:
                    # Get window position for coordinate adjustment
                    window_geom = self.get_element_geometry(main_window)
                    if window_geom:
                        print(f"Window bounds: {window_geom}")
                        self.window_offset = {
                            'x': window_geom['x'],
                            'y': window_geom['y']
                        }
                    else:
                        self.window_offset = {'x': 0, 'y': 0}
                    root = main_window
                else:
                    self.window_offset = {'x': 0, 'y': 0}
                    root = app_ref
            except:
                self.window_offset = {'x': 0, 'y': 0}
                root = app_ref
            
            # Don't assign numbers during scanning
            self.element_counter = 0  # We'll number after sorting
            elements = self.scan_children(root)
            
            # Sort elements by position: BOTTOM-to-TOP, left-to-right (flipped)
            def sort_key(element):
                # Use element.y directly (higher Y = lower on screen in AX coordinates)
                # Sort by Y descending (bottom to top), then X ascending (left to right)
                return (-element.y, element.x)  # Negative Y to reverse the order
            
            elements.sort(key=sort_key)
            
            # Now assign numbers in visual order
            for i, element in enumerate(elements, 1):
                element.number = i
            
            print(f"Found {len(elements)} interactive elements (sorted by position)")
            return elements
            
        except Exception as e:
            print(f"Scan error: {e}")
            return []


class SimpleOverlay(QWidget):
    def __init__(self, elements: List[UIElement], scanner):
        super().__init__()
        self.elements = elements
        self.scanner = scanner
        self.number_input = NumberInput(self)
        self.rescan_timer = QTimer()
        self.rescan_timer.timeout.connect(self.rescan_and_refresh)
        self.rescan_timer.setSingleShot(True)
        self.setup_ui()

    def setup_ui(self):
        # Make window transparent and always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Enable keyboard focus
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        
        # Cover whole screen
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        
        self.create_badges()
        self.setup_shortcuts()
        self.show()
        
        # Ensure the overlay gets focus
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def create_badges(self):
        """Create badges for current elements."""
        # Clear existing badges
        for child in self.findChildren(AppleBadge):
            child.deleteLater()
        
        # Get screen info for coordinate conversion
        screens = NSScreen.screens()
        main_screen = screens[0]
        screen_frame = main_screen.frame()
        screen_height = screen_frame.size.height
        
        print(f"Screen: {screen_frame.size.width}x{screen_frame.size.height}")
        
        # Get screen geometry
        screen = QApplication.primaryScreen().geometry()
        
        # Create Apple-style badges
        for element in self.elements:
            # AX coordinates are already in screen space for macOS
            # No coordinate conversion needed - use AX coordinates directly
            qt_x = element.x
            qt_y = element.y
            
            # Calculate element center
            element_center_x = qt_x + element.width / 2
            element_center_y = qt_y + element.height / 2
            
            # Create Apple-style badge with element center information and role
            badge = AppleBadge(str(element.number), element_center_x, element_center_y, element.role, self)
            
            # Position badge relative to element with offset
            badge_x = int(qt_x - 20)  # Further offset to the left
            badge_y = int(qt_y - 30)  # Further above the element
            
            # Ensure badges stay on screen
            badge_x = max(0, min(badge_x, screen.width() - badge.width()))
            badge_y = max(0, min(badge_y, screen.height() - badge.height()))
            
            badge.move(badge_x, badge_y)
            badge.show()
            
            print(f"Element {element.number}: AX({element.x:.0f},{element.y:.0f}) -> Qt({qt_x:.0f},{qt_y:.0f}) -> Badge({badge_x},{badge_y}) -> Role: {element.role}")

    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Clear existing shortcuts
        for shortcut in self.findChildren(QShortcut):
            shortcut.deleteLater()
        
        # Setup escape to exit
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.activated.connect(self.close)
        
        # Setup digit input (0-9)
        for digit in range(10):
            shortcut = QShortcut(QKeySequence(str(digit)), self)
            shortcut.activated.connect(lambda d=digit: self.number_input.add_digit(d))

        # Setup backspace to clear input
        backspace = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        backspace.activated.connect(self.number_input.clear_input)

    def activate_element(self, number):
        """Activate element by number and rescan after UI changes."""
        print(f"🔍 Looking for element {number}...")
        found = False
        for element in self.elements:
            if element.number == number:
                found = True
                try:
                    print(f"🎯 Activating element {number}: {element.role} at ({element.x}, {element.y})")
                    print(f"📏 Size: {element.width} x {element.height}")
                    
                    # Debug the element to understand why it might not be clickable
                    self.debug_mail_element(element)
                    
                    # Try to click the element with AX first
                    result = AXUIElementPerformAction(element.ax_element, kAXPressAction)
                    print(f"🔧 AX Click result: {result}")
                    
                    if result == 0:  # Success
                        print(f"✅ AX click worked for element {number}")
                        self.rescan_timer.start(1500)
                    else:
                        print(f"⚠️ AX click failed ({result}), trying mouse click...")
                        # For Mail, try different approach
                        self.try_mail_specific_click(element)
                    return
                except Exception as e:
                    print(f"❌ Failed to activate element {number}: {e}")
                    return
        
        if not found:
            print(f"❌ Element {number} not found. Available range: 1-{len(self.elements)}")
            if len(self.elements) > 0:
                max_elem = max(elem.number for elem in self.elements)
                print(f"📊 Total elements: {len(self.elements)}, highest number: {max_elem}")

    def debug_mail_element(self, element):
        """Debug Mail-specific element properties."""
        try:
            print(f"🔍 Mail Element Analysis:")
            print(f"   🏷️ Role: {element.role}")
            
            # Check if element is enabled
            try:
                _, enabled = AXUIElementCopyAttributeValue(element.ax_element, 'AXEnabled', None)
                print(f"   ✅ Enabled: {enabled}")
            except:
                print(f"   ❓ Enabled: Unknown")
            
            # Check available actions
            try:
                _, actions = AXUIElementCopyAttributeValue(element.ax_element, 'AXActions', None)
                if actions:
                    print(f"   🎬 Available actions: {list(actions)}")
                else:
                    print(f"   🎬 No actions available")
            except:
                print(f"   🎬 Actions: Unknown")
            
            # Check if it's focused
            try:
                _, focused = AXUIElementCopyAttributeValue(element.ax_element, 'AXFocused', None)
                print(f"   🎯 Focused: {focused}")
            except:
                print(f"   🎯 Focused: Unknown")
                
            # Check parent element
            try:
                _, parent = AXUIElementCopyAttributeValue(element.ax_element, 'AXParent', None)
                if parent:
                    _, parent_role = AXUIElementCopyAttributeValue(parent, 'AXRole', None)
                    print(f"   👨‍👩‍👧‍👦 Parent: {parent_role}")
                else:
                    print(f"   👨‍👩‍👧‍👦 No parent")
            except:
                print(f"   👨‍👩‍👧‍👦 Parent: Unknown")
                
        except Exception as e:
            print(f"🔧 Debug failed: {e}")

    def try_mail_specific_click(self, element):
        """Try Mail-specific clicking methods."""
        try:
            print("🖱️ Trying Mail-specific click methods...")
            
            # Method 1: Try to focus the element first, then click
            print("🎯 Method 1: Focus then click")
            try:
                # Set focus to the element
                focus_result = AXUIElementPerformAction(element.ax_element, 'AXFocus')
                print(f"   Focus result: {focus_result}")
                
                if focus_result == 0:
                    # Now try to press
                    press_result = AXUIElementPerformAction(element.ax_element, kAXPressAction)
                    print(f"   Press after focus result: {press_result}")
                    if press_result == 0:
                        print("   ✅ Focus+Press worked!")
                        self.rescan_timer.start(1500)
                        return
            except Exception as e:
                print(f"   ❌ Focus+Press failed: {e}")
            
            # Method 2: Try different AX actions
            print("🎯 Method 2: Try different actions")
            actions_to_try = ['AXPick', 'AXShowMenu', 'AXSelect']
            for action in actions_to_try:
                try:
                    result = AXUIElementPerformAction(element.ax_element, action)
                    print(f"   {action} result: {result}")
                    if result == 0:
                        print(f"   ✅ {action} worked!")
                        self.rescan_timer.start(1500)
                        return
                except Exception as e:
                    print(f"   ❌ {action} failed: {e}")
            
            # Method 3: Try clicking the parent element
            print("🎯 Method 3: Click parent element")
            try:
                _, parent = AXUIElementCopyAttributeValue(element.ax_element, 'AXParent', None)
                if parent:
                    result = AXUIElementPerformAction(parent, kAXPressAction)
                    print(f"   Parent click result: {result}")
                    if result == 0:
                        print("   ✅ Parent click worked!")
                        self.rescan_timer.start(1500)
                        return
            except Exception as e:
                print(f"   ❌ Parent click failed: {e}")
            
            # Method 4: Simple mouse click (the fallback)
            print("🎯 Method 4: Simple mouse click")
            self.try_alternative_click(element)
            
        except Exception as e:
            print(f"❌ All Mail-specific methods failed: {e}")

    def debug_element(self, element):
        """Debug information about an element."""
        try:
            print(f"🔍 Element debugging:")
            print(f"   📍 Position: ({element.x}, {element.y})")
            print(f"   📏 Size: {element.width} x {element.height}")
            print(f"   🏷️ Role: {element.role}")
            print(f"   📝 Title: '{element.title}'" if element.title else "   📝 No title")
            
            # Try to get more attributes
            try:
                _, enabled = AXUIElementCopyAttributeValue(element.ax_element, 'AXEnabled', None)
                print(f"   ✅ Enabled: {enabled}")
            except:
                print(f"   ❓ Enabled: Unknown")
            
            try:
                _, description = AXUIElementCopyAttributeValue(element.ax_element, 'AXDescription', None)
                print(f"   📄 Description: '{description}'" if description else "   📄 No description")
            except:
                print(f"   📄 Description: None")
                
            try:
                _, value = AXUIElementCopyAttributeValue(element.ax_element, 'AXValue', None)
                print(f"   💎 Value: '{value}'" if value else "   💎 No value")
            except:
                print(f"   💎 Value: None")
                
        except Exception as e:
            print(f"🔧 Debug failed: {e}")

    def try_alternative_click(self, element):
        """Simple mouse click that was working before."""
        try:
            print("🖱️ Using the simple method that was working...")
            center_x = element.x + element.width / 2
            center_y = element.y + element.height / 2
            
            print(f"🎯 Clicking at: ({center_x}, {center_y})")
            
            # Import mouse control
            try:
                from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGHIDEventTap
                import time
                
                # Create mouse down event
                mouse_down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, (center_x, center_y), 0)
                # Create mouse up event  
                mouse_up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, (center_x, center_y), 0)
                
                # Post the events
                CGEventPost(kCGHIDEventTap, mouse_down)
                time.sleep(0.05)  # Short delay
                CGEventPost(kCGHIDEventTap, mouse_up)
                
                print(f"✅ Mouse click sent to ({center_x}, {center_y})")
                
                # Wait for UI update
                print("⏳ Waiting for UI to update...")
                self.rescan_timer.start(1500)
                
            except ImportError:
                print("❌ Quartz not available for mouse clicking")
                
        except Exception as e:
            print(f"❌ Click failed: {e}")

    def try_accessibility_click(self, element):
        """Try different accessibility actions."""
        print("🔧 Trying different accessibility actions...")
        
        # List of actions to try
        actions_to_try = [
            'AXPress',  # Standard press
            'AXPick',   # Alternative pick action
            'AXShowMenu',  # Show context menu
        ]
        
        for action in actions_to_try:
            try:
                print(f"🔧 Trying action: {action}")
                # Get available actions for this element
                _, available_actions = AXUIElementCopyAttributeValue(element.ax_element, 'AXRole', None)
                print(f"🔧 Element role: {available_actions}")
                
                # Try the action
                from ApplicationServices import AXUIElementPerformAction
                result = AXUIElementPerformAction(element.ax_element, action)
                print(f"🔧 Action {action} result: {result}")
                
                if result == 0:  # Success
                    print(f"✅ Action {action} succeeded!")
                    self.rescan_timer.start(2000)
                    return
                    
            except Exception as e:
                print(f"🔧 Action {action} failed: {e}")
                continue
        
        print("❌ All accessibility actions failed")

    def rescan_and_refresh(self):
        """Rescan the UI and refresh the overlay with new elements."""
        print("\n" + "="*50)
        print("🔄 Rescanning UI for changes...")
        print("="*50)
        
        # Focus back to target app first
        if self.scanner.focus_target_app():
            # Small delay to let the app come to front
            import time
            time.sleep(0.5)
        
        # Scan the target app (not whatever is currently frontmost)
        new_elements = self.scanner.scan_app(use_target_app=True)
        
        if new_elements:
            print(f"✅ Found {len(new_elements)} new elements")
            self.elements = new_elements
            self.create_badges()
            
            # Clear any pending input
            self.number_input.clear_input()
            
            print(f"\n🎯 Overlay refreshed with {len(self.elements)} elements")
            print("Type any number to activate elements, ESC to exit")
        else:
            print("❌ No elements found in rescan")

    def keyPressEvent(self, event):
        """Handle key press events."""
        # Clear input on escape
        if event.key() == Qt.Key.Key_Escape:
            self.number_input.clear_input()
        super().keyPressEvent(event)


def main():
    print("Apple Voice Control Style Overlay - Continuous Mode")
    print("=" * 50)
    print("🚀 Starting continuous interaction mode...")
    print("📱 Click elements → UI updates → Get new numbers → Repeat!")
    print("⚡ Press ESC anytime to exit")
    print("=" * 50)
    print("⏰ Starting in 3 seconds... Switch to your target application now!")
    time.sleep(3)
    
    scanner = SimpleScanner()
    
    # Test permissions first
    print("Testing permissions...")
    if not scanner.test_permissions():
        print("\n🚨 Accessibility permissions needed!")
        print("Go to System Settings > Privacy & Security > Accessibility")
        print("Add Terminal and enable it")
        return
    
    # Scan for initial elements (this will set the target app)
    print("Performing initial scan...")
    elements = scanner.scan_app(use_target_app=False)  # First scan sets the target
    
    if not elements:
        print("No elements found. Try a different application.")
        return
    
    # Create persistent overlay
    app = QApplication(sys.argv)
    overlay = SimpleOverlay(elements, scanner)
    
    print(f"\n🎯 Overlay ready with {len(elements)} elements")
    print(f"📌 Locked to: {scanner.target_app_name}")
    print("📋 CONTINUOUS MODE ACTIVE:")
    print("   • Type numbers to click elements")
    print("   • UI will auto-refresh after clicks")
    print("   • Numbers will update for new screens")
    print("   • Always stays in the same app")
    print("   • Press ESC to exit anytime")
    print("=" * 50)
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("Exiting...")


if __name__ == "__main__":
    main()