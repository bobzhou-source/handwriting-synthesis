# -*- coding: utf-8 -*-
"""
Enhanced version of gui.py with proper layout proportions, background selection, queue features,
and text wrapping around images
"""
from demo import Hand
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter import ttk
from tkcolorpicker import askcolor
from PIL import ImageTk, Image
import subprocess
import os
import sys
from threading import Thread
import time
import math
from svg2png import svg2png, fulltrim
import shutil
import string
import random
from resourcepath import resourcepath
import textwrap
import json
from datetime import datetime

# Import for PDF generation
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: reportlab not available. PDF export will be disabled.")

class ModernFrame(ttk.Frame):
    """A frame with a title, separator, and stylized appearance"""
    def __init__(self, parent, title, **kwargs):
        ttk.Frame.__init__(self, parent, **kwargs)
        
        # Create a frame for the title with padding
        title_frame = ttk.Frame(self, padding=(10, 5))
        title_frame.pack(fill="x", anchor="nw")
        
        # Add title label with larger, bold font
        title_label = ttk.Label(title_frame, text=title, font=('Helvetica', 16, 'bold'))
        title_label.pack(side="left", anchor="w", padx=5)
        
        # Add separator below title
        separator = ttk.Separator(self, orient="horizontal")
        separator.pack(fill="x", padx=5, pady=(0, 10))
        
        # Create a content frame with padding
        self.content_frame = ttk.Frame(self, padding=(15, 5, 15, 10))
        self.content_frame.pack(fill="both", expand=True)

class ScrollableFrame(ttk.Frame):
    """A frame with a scrollbar that automatically appears when needed"""
    def __init__(self, parent, **kwargs):
        ttk.Frame.__init__(self, parent, **kwargs)
        
        # Create a canvas with scrollbar
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # Performance optimization: reduce redraws
        self._update_pending = False
        self._last_height = 0
        self._resize_after_id = None
        self._suspended = False
        self._last_canvas_width = None
        
        # Configure canvas with throttled updates
        self.scrollable_frame.bind(
            "<Configure>",
            self._throttled_configure
        )
        
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Pack widgets - always keep scrollbar visible to reduce layout churn
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Update scroll region when the size of the frame changes (debounced)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        
    def suspend(self, flag: bool):
        """Temporarily pause scrollregion/width updates (used during window resize drags)."""
        self._suspended = bool(flag)

    def _throttled_configure(self, event):
        """Throttle configure events to prevent excessive redraws"""
        if self._suspended:
            return
        if not self._update_pending:
            self._update_pending = True
            self.after_idle(self._do_configure_update)
    
    def _do_configure_update(self):
        """Actually perform the configure update"""
        try:
            bbox = self.canvas.bbox("all")
            if bbox:  # bbox can be None before first layout
                self.canvas.configure(scrollregion=bbox)
        finally:
            self._update_pending = False
        
    def on_canvas_resize(self, event):
        if self._suspended:
            return
        # Skip if width didn't actually change
        if self._last_canvas_width == event.width:
            return
        self._last_canvas_width = event.width

        after_id = getattr(self, "_resize_after_id", None)
        if after_id:
            self.after_cancel(after_id)

        new_w = event.width
        def apply_resize():
            # Only touch width if still current
            if self._last_canvas_width == new_w:
                self.canvas.itemconfig(self.canvas_frame, width=new_w)
                bbox = self.canvas.bbox("all")
                last_bbox = getattr(self, "_last_bbox", None)
                if bbox != last_bbox:
                    self.canvas.configure(scrollregion=bbox)
                    self._last_bbox = bbox
            self._resize_after_id = None

        self._resize_after_id = self.after(80, apply_resize)

class QueueItem:
    """Class to store information about a queued text item"""
    def __init__(self, text, name=None):
        self.text = text
        if name:
            self.name = name
        else:
            # Create a short preview of the text (first 20 chars)
            preview = text.strip()[:20]
            if len(text.strip()) > 20:
                preview += "..."
            self.name = preview

class MyWindow:
    def __init__(self, win):
        self.root = win
        self.text = ''
        self.stylelabel = None
        self.colorlabel = None
        self.colortextlabel = None
        self.hand = None
        self.styles = []
        self.currentstyle = 0
        self.stroke_color = '#003264'      
        self.valid_chars = ['"', '6', 'G', 'b', ')', 'I', '0', 'O', 'c', '9', 'L', '8', 't', 'q', 's', '\x00', 'U', 'S', 'W', 'a', 'k', '2', 'B', 'M', '7', 'T', 'g', 'f', 'F', 'P', 'l', 'E', 'v', 'y', 'j', 'Y', 'J', '-', 'R', '!', '#', '.', 'o', 'r', '?', 'C', "'", '5', 'm', 'h', '4', 'A', 'u', 'p', 'w', 'n', '(', 'V', 'd', '1', ',', 'H', 'i', 'x', ';', ':', 'z', 'K', '3', 'N', ' ', 'D', 'e', '\n']
        
        # Add auto-remove invalid chars option
        self.auto_remove_invalid = tk.BooleanVar(value=False)
        
        # Add variables for slider values
        self.legibility_value = tk.StringVar(value="50")
        self.stroke_width_value = tk.StringVar(value="5.0")
        
        # Initialize text queue
        self.text_queue = []
        self.processing_queue = False
        self.current_queue_index = 0
        
        # Background settings
        self.background_type = tk.StringVar(value="white")
        self.background_color = "#FFFFFF"  # Default: white
        self.background_image_path = None
        
        # Export format settings
        self.export_format = tk.StringVar(value="png")  # Default: PNG
        self.jpg_quality = tk.IntVar(value=95)  # Default JPG quality
        
        # Image placement settings
        self.image_path = None
        self.image_obj = None
        self.image_x = tk.IntVar(value=400)  # Default X position
        self.image_y = tk.IntVar(value=200)  # Default Y position
        self.image_width = tk.IntVar(value=300)  # Default width
        self.image_height = tk.IntVar(value=300)  # Default height
        self.image_wrap_style = tk.StringVar(value="both")  # Default wrap style (both sides)
        self.image_enabled = tk.BooleanVar(value=False)  # Whether to use image placement
    
        # Cancellation and error flags
        self._cancel = False
        self._errors = []

        # Mini-preview state
        self._mini_prev_after = None
        self._mini_prev_img = None

        # Load style images with caching and optimization
        self.styles = []
        self.style_images_cache = {}  # Cache for PhotoImage objects
        self.load_style_images()
        
        # Create main container that will have fixed proportions
        self.main_container = ttk.Frame(win)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Set grid weight to maintain proportions during resize
        self.main_container.columnconfigure(0, weight=1, minsize=300)  # Left panel
        self.main_container.columnconfigure(1, weight=1, minsize=300)  # Right panel
        self.main_container.columnconfigure(2, weight=2, minsize=500)  # Text input area
        self.main_container.rowconfigure(0, weight=1)
        
        # Create scrollable panels for controls
        self.left_panel = ScrollableFrame(self.main_container)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        self.right_panel = ScrollableFrame(self.main_container)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=5)
        
        # Text input area
        self.text_frame = ttk.Frame(self.main_container)
        self.text_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        
        # Create controls in nice frames with titles (with lazy loading optimization)
        self.create_writing_parameters(self.left_panel.scrollable_frame)
        self.create_style_section(self.left_panel.scrollable_frame)
        self.create_color_section(self.left_panel.scrollable_frame)
        
        # Defer creation of right panel sections to improve startup
        self.root.after(50, self.create_right_panel_sections)
        
        self.create_text_input_section(self.text_frame)
        
        # Set style initially
        self.set_style(win, 0, None)
        
        # Update scrollbar visibility after a short delay
        win.after(100, self.update_scrollbars)
        
        # Coalesce root Configure events and pause heavy updates during drag
        win.bind("<Configure>", self._on_root_configure)
        self._resize_done_after_id = None
        self._resizing = False
        
        # Add window state management for better performance
        self.window_state = "normal"
        self.is_minimized = False
        self.performance_mode = False  # Enable performance optimizations
        win.bind("<Map>", self.on_window_map)
        win.bind("<Unmap>", self.on_window_unmap)
        win.bind("<FocusIn>", self.on_window_focus)
        win.bind("<FocusOut>", self.on_window_focus_out)
        
        # Add performance monitoring
        self.update_count = 0
        self.last_update_time = time.time()
        
        # Thread-safe UI helper
        self._cfg_after_id = None
        self._resize_after_id = None
        
        # load saved user preferences
        self.load_prefs()
        
        # Trigger initial live preview
        self._queue_mini_preview()

    def _prefs_path(self):
        # keep alongside app resources
        return resourcepath(".userprefs.json")

    def save_prefs(self):
        data = dict(
            currentstyle=self.currentstyle,
            stroke_color=self.stroke_color,
            legibility=float(self.legibilityscale.get()),
            stroke_width=float(self.widthscale.get()),
            line_width=int(self.get_max_line_width()),
            line_spacing=float(self.lineheightscale.get()),
            background_type=self.background_type.get(),
            background_color=self.background_color,
            export_format=self.export_format.get(),
            jpg_quality=int(self.jpg_quality.get()),
            image_enabled=bool(self.image_enabled.get()),
            image_x=int(self.image_x.get()),
            image_y=int(self.image_y.get()),
            image_w=int(self.image_width.get()),
            image_h=int(self.image_height.get()),
        )
        try:
            with open(self._prefs_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # don’t crash on close

    def load_prefs(self):
        try:
            with open(self._prefs_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            self.set_style(self.root, d.get("currentstyle", 0))
            self.stroke_color = d.get("stroke_color", self.stroke_color)
            self.legibilityscale.set(d.get("legibility", 50))
            self.widthscale.set(d.get("stroke_width", 5))
            lw = int(d.get("line_width", 43))
            self.custom_width_var.set(str(lw))
            self.linewidthscale.set(lw)
            self.lineheightscale.set(d.get("line_spacing", 80))
            self.background_type.set(d.get("background_type", "white"))
            self.background_color = d.get("background_color", "#FFFFFF")
            self.export_format.set(d.get("export_format", "png"))
            self.jpg_quality.set(d.get("jpg_quality", 95))
            self.image_enabled.set(d.get("image_enabled", False))
            self.image_x.set(d.get("image_x", 400))
            self.image_y.set(d.get("image_y", 200))
            self.image_width.set(d.get("image_w", 300))
            self.image_height.set(d.get("image_h", 300))
            # refresh dependent UI
            self.update_background_options()
            self.update_export_format_options()
            self.update_image_placement_options()
            # update color swatch
            self.choose_color(self.root, usercolor=False)
        except Exception:
            pass
    
    def _on_root_configure(self, event):
        # First tick of a drag: enter "suspended" mode
        if not self._resizing:
            self._resizing = True
            # Pause expensive canvas updates
            self.left_panel.suspend(True)
            self.right_panel.suspend(True)
            # (Optional) pause text reflow too for big docs
            try:
                self.inputtext.configure(state="disabled")
            except Exception:
                pass

        # Push out the "resize finished" task
        if self._resize_done_after_id:
            self.root.after_cancel(self._resize_done_after_id)
        # Run after the drag quiesces for ~180ms
        self._resize_done_after_id = self.root.after(180, self._on_root_resize_done)

    def _on_root_resize_done(self):
        self._resizing = False
        # Resume updates and do one clean pass
        self.left_panel.suspend(False)
        self.right_panel.suspend(False)
        self.update_scrollbars()  # one bbox/scrollregion compute, not dozens

        # Re-enable text reflow
        try:
            self.inputtext.configure(state="normal")
        except Exception:
            pass
    
    def ui(self, fn, *args, **kwargs):
        """Thread-safe UI update helper - ensures all UI operations happen on main thread"""
        self.root.after(0, lambda: fn(*args, **kwargs))
    
    def step_bar_after(self, bar, total, steps=50, delay_ms=15):
        """After-driven progress bar that doesn't block the UI thread"""
        i = {"done": 0}
        def tick():
            if i["done"] >= steps: 
                return
            bar.step(total/steps)
            i["done"] += 1
            self.root.after(delay_ms, tick)
        self.root.after(0, tick)
    
    def show_preview_after_dialog(self):
        """Show preview after dialog is destroyed to prevent stalling"""
        if hasattr(self, 'preview_info') and self.preview_info['show_preview']:
            output_files = self.preview_info['output_files']
            final_output = self.preview_info['final_output']
            export_format = self.preview_info['export_format']
            
            if output_files:
                # Use the first output file for preview
                output_file_path = output_files[0]
                
                if self.preview_option.get() == "both":
                    # Show both the image and file explorer
                    if export_format != "pdf":  # Only show image for non-PDF formats
                        final_output.show()
                    self.show_file(os.path.abspath(output_file_path))
                elif self.preview_option.get() == "image_viewer":
                    # Only show the image viewer (skip for PDF)
                    if export_format != "pdf":
                        final_output.show()
                elif self.preview_option.get() == "file_explorer":
                    # Only show in file explorer
                    self.show_file(os.path.abspath(output_file_path))
    
    def _debounced_update_scrollbars(self):
        """Debounced scrollbar update to prevent storm of Configure events"""
        if self.is_minimized:
            return
        if self._cfg_after_id: 
            self.root.after_cancel(self._cfg_after_id)
        self._cfg_after_id = self.root.after(150, self.update_scrollbars)
        
    def update_scrollbars(self):
        current_time = time.time()
        if current_time - self.last_update_time < 0.12 or self.is_minimized or not self.root.winfo_viewable():
            return
        self.update_count += 1
        self.last_update_time = current_time
        try:
            # Only touch if bbox changed
            for panel in (self.left_panel, self.right_panel):
                bbox = panel.canvas.bbox("all")
                if getattr(panel, "_last_bbox_force", None) != bbox:
                    panel.canvas.configure(scrollregion=bbox)
                    panel._last_bbox_force = bbox
        except Exception as e:
            print(f"Error updating scrollbars: {e}")
    
    def load_style_images(self):
        """Load style images with optimization and caching"""
        try:
            for i in range(12):
                # Load and crop image
                styleimage = Image.open(resourcepath(f"gui/stylebook/images/{i}.png")).crop((400, 30, 620, 90))
                self.styles.append(styleimage)
                
                # Pre-create PhotoImage for faster access
                photo = ImageTk.PhotoImage(styleimage)
                self.style_images_cache[i] = photo
        except Exception as e:
            print(f"Error loading style images: {e}")
            # Create placeholder images if loading fails
            for i in range(12):
                placeholder = Image.new('RGB', (220, 60), color='lightgray')
                self.styles.append(placeholder)
                photo = ImageTk.PhotoImage(placeholder)
                self.style_images_cache[i] = photo
    
    def on_window_map(self, event):
        """Handle window being restored/mapped"""
        if self.is_minimized:
            self.is_minimized = False
            # Defer UI updates to prevent lag
            self.root.after(50, self.refresh_ui_after_restore)
    
    def on_window_unmap(self, event):
        """Handle window being minimized/unmapped"""
        self.is_minimized = True
    
    def on_window_focus(self, event):
        """Handle window gaining focus"""
        pass  # Could add focus-based optimizations here
    
    def on_window_focus_out(self, event):
        """Handle window losing focus"""
        pass  # Could add focus-based optimizations here
    
    def refresh_ui_after_restore(self):
        """Refresh UI elements after window restore to prevent lag"""
        try:
            # Only update if window is visible
            if self.root.winfo_viewable():
                # Update scrollbars
                self.update_scrollbars()
                # Force a gentle refresh of the canvas
                if hasattr(self, 'left_panel') and hasattr(self.left_panel, 'canvas'):
                    self.left_panel.canvas.update_idletasks()
                if hasattr(self, 'right_panel') and hasattr(self.right_panel, 'canvas'):
                    self.right_panel.canvas.update_idletasks()
        except Exception as e:
            print(f"Error refreshing UI: {e}")
    
    def create_right_panel_sections(self):
        """Create right panel sections with lazy loading for better startup performance"""
        try:
            self.create_text_layout_section(self.right_panel.scrollable_frame)
            self.create_text_options_section(self.right_panel.scrollable_frame)
            self.create_background_section(self.right_panel.scrollable_frame)
            self.create_image_placement_section(self.right_panel.scrollable_frame)
            self.create_queue_section(self.right_panel.scrollable_frame)
            
            # Update scrollbars after sections are created
            self.root.after(100, self.update_scrollbars)
        except Exception as e:
            print(f"Error creating right panel sections: {e}")

    def create_writing_parameters(self, parent):
        # Writing Parameters Section
        self.writing_frame = ModernFrame(parent, "Writing Parameters")
        self.writing_frame.pack(fill="x", pady=(0, 15))
        
        # Add content to the frame
        content = self.writing_frame.content_frame
        
        # Legibility slider
        legibility_header = ttk.Frame(content)
        legibility_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(legibility_header, text="Legibility").pack(side="left")
        ttk.Label(legibility_header, textvariable=self.legibility_value).pack(side="right")
        
        legibility_frame = ttk.Frame(content)
        legibility_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        
        ttk.Label(legibility_frame, text="Illegible").pack(side="left", padx=(0, 5))
        self.legibilityscale = ttk.Scale(
            legibility_frame, 
            length=150, 
            from_=0, 
            to=100, 
            orient=tk.HORIZONTAL, 
            value=50,
            command=self.update_legibility_value
        )
        self.legibilityscale.pack(side="left", expand=True, fill="x", padx=5)
        ttk.Label(legibility_frame, text="Legible").pack(side="left", padx=(5, 0))
        
        # Stroke Width slider
        width_header = ttk.Frame(content)
        width_header.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(width_header, text="Stroke Width").pack(side="left")
        ttk.Label(width_header, textvariable=self.stroke_width_value).pack(side="right")
        
        width_frame = ttk.Frame(content)
        width_frame.grid(row=3, column=0, sticky="ew")
        
        ttk.Label(width_frame, text="Thin").pack(side="left", padx=(0, 5))
        self.widthscale = ttk.Scale(
            width_frame, 
            length=150, 
            from_=0, 
            to=10, 
            orient=tk.HORIZONTAL, 
            value=5,
            command=self.update_stroke_width_value
        )
        self.widthscale.pack(side="left", expand=True, fill="x", padx=5)
        ttk.Label(width_frame, text="Thick").pack(side="left", padx=(5, 0))

    def create_style_section(self, parent):
        # Style Section
        self.style_frame = ModernFrame(parent, "Writing Style")
        self.style_frame.pack(fill="x", pady=(0, 15))
        
        # Add content to the frame
        content = self.style_frame.content_frame
        
        # Style preview
        self.style_preview_frame = ttk.Frame(content, borderwidth=2, relief="sunken", padding=5)
        self.style_preview_frame.pack(fill="x", pady=(0, 10))
        
        # Style button
        self.stylebookbtn = ttk.Button(content, text='Change Style', command=lambda: self.open_stylebook(parent.winfo_toplevel()))
        self.stylebookbtn.pack(anchor="center", pady=(0, 5))

        self.mini_preview_label = ttk.Label(content, text=" ")
        self.mini_preview_label.pack(anchor="center", pady=(4,0))
    
    def create_image_placement_section(self, parent):
        # Image Placement Section
        self.image_frame = ModernFrame(parent, "Image Placement")
        self.image_frame.pack(fill="x", pady=(0, 15))
        
        # Add content to the frame
        content = self.image_frame.content_frame
        
        # Enable/disable image placement
        enable_frame = ttk.Frame(content)
        enable_frame.pack(fill="x", pady=(0, 10))
        
        self.image_enabled_check = ttk.Checkbutton(
            enable_frame,
            text="Enable Image Placement",
            variable=self.image_enabled,
            command=self.update_image_placement_options
        )
        self.image_enabled_check.pack(anchor="w")
        
        # Image selection
        image_select_frame = ttk.Frame(content)
        image_select_frame.pack(fill="x", pady=(0, 10))
        
        # Show selected image path or "No image selected"
        self.image_path_label = ttk.Label(
            image_select_frame,
            text="No image selected",
            wraplength=200
        )
        self.image_path_label.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # Browse button
        self.image_browse_btn = ttk.Button(
            image_select_frame,
            text="Browse...",
            command=self.choose_placement_image
        )
        self.image_browse_btn.pack(side="right")
        
        # Interactive placement canvas
        self.placement_canvas = tk.Canvas(content, width=300, height=180, highlightthickness=1, relief="sunken")
        self.placement_canvas.pack(fill="x", pady=(0,10))
        self._lock_aspect = tk.BooleanVar(value=True)

        # controls row
        lock_row = ttk.Frame(content); lock_row.pack(fill="x", pady=(0,5))
        ttk.Checkbutton(lock_row, text="Lock aspect ratio", variable=self._lock_aspect).pack(side="left")

        # internal state for drag/resize
        self._dragging = None  # "move" or "resize"
        self._drag_off = (0,0)
        self._rect_id = None
        self._preview_scale = 1.0

        # bindings
        self.placement_canvas.bind("<Button-1>", self._place_on_press)
        self.placement_canvas.bind("<B1-Motion>", self._place_on_drag)
        self.placement_canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_dragging", None))
        self.placement_canvas.bind("<KeyPress>", self._place_on_keys)
        self.placement_canvas.focus_set()

        # Position and size controls
        position_frame = ttk.Frame(content)
        position_frame.pack(fill="x", pady=(0, 10))
        
        # X position
        ttk.Label(position_frame, text="X Position:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        x_entry = ttk.Entry(position_frame, width=6, textvariable=self.image_x)
        x_entry.grid(row=0, column=1, padx=(0, 10))
        
        # Y position
        ttk.Label(position_frame, text="Y Position:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        y_entry = ttk.Entry(position_frame, width=6, textvariable=self.image_y)
        y_entry.grid(row=0, column=3)
        
        # Width
        ttk.Label(position_frame, text="Width:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(5, 0))
        width_entry = ttk.Entry(position_frame, width=6, textvariable=self.image_width)
        width_entry.grid(row=1, column=1, padx=(0, 10), pady=(5, 0))
        
        # Height
        ttk.Label(position_frame, text="Height:").grid(row=1, column=2, sticky="w", padx=(0, 5), pady=(5, 0))
        height_entry = ttk.Entry(position_frame, width=6, textvariable=self.image_height)
        height_entry.grid(row=1, column=3, pady=(5, 0))
        
        # Text wrap style
        wrap_frame = ttk.Frame(content)
        wrap_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Label(wrap_frame, text="Text Wrap Style:").pack(anchor="w", pady=(0, 5))
        
        # Wrap style options
        wrap_options = ttk.Frame(wrap_frame)
        wrap_options.pack(fill="x")
        
        ttk.Radiobutton(
            wrap_options,
            text="Left of Image",
            variable=self.image_wrap_style,
            value="left"
        ).grid(row=0, column=0, sticky="w")
        
        ttk.Radiobutton(
            wrap_options,
            text="Right of Image",
            variable=self.image_wrap_style,
            value="right"
        ).grid(row=1, column=0, sticky="w")
        
        ttk.Radiobutton(
            wrap_options,
            text="Both Sides",
            variable=self.image_wrap_style,
            value="both"
        ).grid(row=2, column=0, sticky="w")
        
        # Initially update the UI based on the default values
        self.update_image_placement_options()
    
    def _refresh_placement_canvas(self):
        """Redraw rectangle scaled to the preview canvas."""
        c = self.placement_canvas
        if not c: return
        c.delete("all")
        # simple paper bounds model (use finalcanvas approx)
        page_w, page_h = 2400, 1600
        cw = int(c.winfo_width() or 300)
        ch = int(c.winfo_height() or 180)
        sx = cw / page_w
        sy = ch / page_h
        s = min(sx, sy)
        self._preview_scale = s

        # draw page outline
        c.create_rectangle(1, 1, int(page_w*s)-1, int(page_h*s)-1, outline="#888")

        # draw placed image rect
        ix = int(self.image_x.get() * s)
        iy = int(self.image_y.get() * s)
        iw = int(self.image_width.get() * s)
        ih = int(self.image_height.get() * s)
        self._rect_id = c.create_rectangle(ix, iy, ix+iw, iy+ih, outline="#2a7", width=2, fill="")
        # resize handles
        r = 5
        for (hx, hy) in [(ix+iw, iy+ih)]:
            c.create_rectangle(hx-r, hy-r, hx+r, hy+r, fill="#2a7", outline="")
        # labels
        c.create_text(8, ch-10, anchor="w",
                      text=f"x={self.image_x.get()}, y={self.image_y.get()}, w={self.image_width.get()}, h={self.image_height.get()}",
                      fill="#666")

    def _hit_test_handle(self, x, y):
        # only bottom-right handle for simplicity
        s = self._preview_scale
        hx = int((self.image_x.get()+self.image_width.get())*s)
        hy = int((self.image_y.get()+self.image_height.get())*s)
        return abs(x - hx) <= 8 and abs(y - hy) <= 8

    def _place_on_press(self, e):
        c = self.placement_canvas
        if self._hit_test_handle(e.x, e.y):
            self._dragging = "resize"
            self._drag_off = (e.x, e.y)
        else:
            self._dragging = "move"
            self._drag_off = (e.x - int(self.image_x.get()*self._preview_scale),
                              e.y - int(self.image_y.get()*self._preview_scale))

    def _place_on_drag(self, e):
        if not self._dragging: return
        s = self._preview_scale
        if self._dragging == "move":
            nx = max(0, int((e.x - self._drag_off[0]) / s))
            ny = max(0, int((e.y - self._drag_off[1]) / s))
            # snap to text-left margin (~400)
            if abs(nx - 400) < 8: nx = 400
            self.image_x.set(nx); self.image_y.set(ny)
        else:  # resize from bottom-right
            nw = max(1, int(e.x / s) - int(self.image_x.get()))
            nh = max(1, int(e.y / s) - int(self.image_y.get()))
            if self._lock_aspect.get():
                # keep last ratio
                ratio = max(1, self.image_width.get()) / max(1, self.image_height.get())
                # fit to whichever is smaller
                if abs(nw/ max(1, nh) - ratio) > 0.01:
                    # adjust nh to match nw
                    nh = max(1, int(nw / ratio))
            self.image_width.set(nw); self.image_height.set(nh)
        self._refresh_placement_canvas()

    def _place_on_keys(self, e):
        # nudge with arrows; Ctrl = ×10
        step = 10 if (e.state & 0x4) else 1
        k = e.keysym
        if k in ("Left","Right","Up","Down"):
            dx = -step if k=="Left" else step if k=="Right" else 0
            dy = -step if k=="Up"   else step if k=="Down"  else 0
            self.image_x.set(max(0, self.image_x.get()+dx))
            self.image_y.set(max(0, self.image_y.get()+dy))
            self._refresh_placement_canvas()
    
    def update_image_placement_options(self):
        """Update the image placement options based on whether it's enabled"""
        enabled = self.image_enabled.get()
        
        # Enable/disable all widgets in the image frame based on the checkbox
        for widget in self.image_frame.content_frame.winfo_children():
            if widget != self.image_enabled_check.master:  # Skip the enable checkbox frame
                for child in widget.winfo_children():
                    if child != self.image_enabled_check:  # Skip the enable checkbox itself
                        # Set the state of widgets
                        if hasattr(child, 'configure'):
                            try:
                                child.configure(state="normal" if enabled else "disabled")
                            except tk.TclError:
                                pass  # Some widgets might not have a state option
        
        self._refresh_placement_canvas()
    
    def update_export_format_options(self):
        """Update the export format options based on selection (grid-aware)."""
        if self.export_format.get() == "jpg":
            # make sure it's visible in the grid
            try:
                self.jpg_quality_frame.grid()  # shows it if previously grid_remove'd
            except Exception:
                pass
        else:
            # hide but keep grid info
            try:
                self.jpg_quality_frame.grid_remove()
            except Exception:
                pass
    
    def create_pdf(self, image, output_path):
        """Create a PDF file from the handwriting image"""
        if not PDF_AVAILABLE:
            raise ImportError("reportlab is required for PDF export. Install it with: pip install reportlab")
        
        # Create PDF canvas
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4
        
        # Convert PIL image to format suitable for reportlab
        if image.mode == 'RGBA':
            # Create white background for transparent images
            white_bg = Image.new('RGB', image.size, 'white')
            white_bg.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
            image = white_bg
        
        # Calculate scaling to fit image on page with margins
        margin = 50
        max_width = width - 2 * margin
        max_height = height - 2 * margin
        
        # Calculate scale factor to fit image
        scale_x = max_width / image.width
        scale_y = max_height / image.height
        scale = min(scale_x, scale_y, 1.0)  # Don't scale up
        
        # Calculate position to center the image
        scaled_width = image.width * scale
        scaled_height = image.height * scale
        x = (width - scaled_width) / 2
        y = (height - scaled_height) / 2
        
        # Draw the image
        c.drawImage(ImageReader(image), x, y, width=scaled_width, height=scaled_height)
        
        # Save the PDF
        c.save()
    
    def create_jpg(self, image, output_path, quality=95):
        """Create a JPG file from the handwriting image"""
        # Convert to RGB if necessary (JPG doesn't support transparency)
        if image.mode in ('RGBA', 'LA'):
            # Create white background
            rgb_image = Image.new('RGB', image.size, 'white')
            if image.mode == 'RGBA':
                rgb_image.paste(image, mask=image.split()[-1])
            else:
                rgb_image.paste(image, mask=image.split()[-1])
            image = rgb_image
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Save as JPG with specified quality
        image.save(output_path, 'JPEG', quality=quality, optimize=True)

    def choose_placement_image(self):
        """Open file dialog to choose an image to place in the handwriting"""
        filetypes = [
            ("Image Files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
            ("All Files", "*.*")
        ]
        
        file_path = filedialog.askopenfilename(
            title="Select Image to Place",
            filetypes=filetypes
        )
        
        if file_path:
            self.image_path = file_path
            self.image_path_label.config(text=file_path)
            
            # Load the image and update size defaults based on image
            try:
                img = Image.open(file_path)
                
                # Set default size based on image, but constrained to reasonable values
                width, height = img.size
                max_width = 600
                max_height = 400
                
                # If image is too large, scale it down maintaining aspect ratio
                if width > max_width or height > max_height:
                    ratio = min(max_width / width, max_height / height)
                    width = int(width * ratio)
                    height = int(height * ratio)
                
                self.image_width.set(width)
                self.image_height.set(height)
                
                # Store the image object
                self.image_obj = img
                
                self._refresh_placement_canvas()
            except Exception as e:
                print(f"Error loading image: {e}")
                messagebox.showerror("Image Error", f"Failed to load image: {e}")

    def create_color_section(self, parent):
        # Color Section
        self.color_frame = ModernFrame(parent, "Font Color")
        self.color_frame.pack(fill="x")
        
        # Add content to the frame
        content = self.color_frame.content_frame
        
        # Color display
        self.color_display_frame = ttk.Frame(content, padding=5)
        self.color_display_frame.pack(fill="x", pady=(0, 10))
        
        # Choose color button
        self.choose_color_btn = ttk.Button(content, text='Change Color', command=lambda: self.choose_color(parent.winfo_toplevel()))
        self.choose_color_btn.pack(anchor="center", pady=(0, 5))
        
        # Initialize color display
        self.choose_color(parent.winfo_toplevel(), False)

    def create_text_layout_section(self, parent):
        # Text Layout Section
        self.layout_frame = ModernFrame(parent, "Text Layout")
        self.layout_frame.pack(fill="x", pady=(0, 15))
        
        # Add content to the frame
        content = self.layout_frame.content_frame
        
        # Text Orientation
        ttk.Label(content, text="Text Alignment").grid(row=0, column=0, sticky="w", pady=(0, 5))
        options = ['Left', 'Middle', 'Right']
        self.orientation = tk.StringVar()
        self.orientation.set('Left')
        orientation_menu = ttk.Combobox(content, textvariable=self.orientation, values=options, state='readonly', width=10)
        orientation_menu.grid(row=0, column=1, pady=(0, 15), sticky="w")
        
        # Max Line Width
        # Create header with value display
        line_width_header = ttk.Frame(content)
        line_width_header.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Label(line_width_header, text="Max Line Width").pack(side="left")
        self.line_width_value = tk.StringVar(value="43")
        ttk.Label(line_width_header, textvariable=self.line_width_value).pack(side="right")
        
        width_frame = ttk.Frame(content)
        width_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        ttk.Label(width_frame, text="10").pack(side="left", padx=(0, 5))
        self.linewidthscale = ttk.Scale(
            width_frame, 
            length=150, 
            from_=10, 
            to=75, 
            orient=tk.HORIZONTAL, 
            value=42.5, 
            command=self.update_line_width_value
        )
        self.linewidthscale.pack(side="left", expand=True, fill="x", padx=5)
        ttk.Label(width_frame, text="75").pack(side="left", padx=(5, 0))
        
        # Custom width entry
        custom_width_frame = ttk.Frame(content)
        custom_width_frame.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 15))
        ttk.Label(custom_width_frame, text="Custom width:").pack(side="left", padx=(0, 5))
        self.custom_width_var = tk.StringVar(value=str(int(self.linewidthscale.get())))
        self.custom_width_entry = ttk.Entry(custom_width_frame, width=8, textvariable=self.custom_width_var)
        self.custom_width_entry.pack(side="left")
        ttk.Label(custom_width_frame, text="chars").pack(side="left", padx=(5, 0))
        
        # Line Spacing with value display
        line_spacing_header = ttk.Frame(content)
        line_spacing_header.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Label(line_spacing_header, text="Line Spacing").pack(side="left")
        self.line_spacing_value = tk.StringVar(value="80")
        ttk.Label(line_spacing_header, textvariable=self.line_spacing_value).pack(side="right")
        
        spacing_frame = ttk.Frame(content)
        spacing_frame.grid(row=5, column=0, columnspan=2, sticky="ew")
        
        ttk.Label(spacing_frame, text="20").pack(side="left", padx=(0, 5))
        self.lineheightscale = ttk.Scale(
            spacing_frame, 
            length=150, 
            from_=20, 
            to=140, 
            orient=tk.HORIZONTAL, 
            value=80,
            command=self.update_line_spacing_value
        )
        self.lineheightscale.pack(side="left", expand=True, fill="x", padx=5)
        ttk.Label(spacing_frame, text="140").pack(side="left", padx=(5, 0))

    def create_text_options_section(self, parent):
        # Text Options Section
        self.options_frame = ModernFrame(parent, "Text Options")
        self.options_frame.pack(fill="x", pady=(0, 15))
        
        # Add content to the frame
        content = self.options_frame.content_frame
        
        # Auto-remove invalid chars
        self.auto_remove_checkbox = ttk.Checkbutton(
            content, 
            text="Auto-remove invalid characters", 
            variable=self.auto_remove_invalid,
            onvalue=True,
            offvalue=False,
            command=self._highlight_invalid
        )
        self.auto_remove_checkbox.pack(anchor="w", pady=5)
        
        # Preview options
        preview_frame = ttk.Frame(content)
        preview_frame.pack(fill="x", pady=5)
        
        ttk.Label(preview_frame, text="Output Preview:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.preview_option = tk.StringVar(value="file_explorer")
        ttk.Radiobutton(
            preview_frame, 
            text="Show in File Explorer", 
            variable=self.preview_option, 
            value="file_explorer"
        ).grid(row=1, column=0, sticky="w")
        
        ttk.Radiobutton(
            preview_frame, 
            text="Show in Image Viewer", 
            variable=self.preview_option, 
            value="image_viewer"
        ).grid(row=2, column=0, sticky="w")
        
        ttk.Radiobutton(
            preview_frame, 
            text="Show Both", 
            variable=self.preview_option, 
            value="both"
        ).grid(row=3, column=0, sticky="w")
        
        # Export format options
        export_frame = ttk.Frame(content)
        export_frame.pack(fill="x", pady=5)
        
        ttk.Label(export_frame, text="Export Format:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        # Export format options
        format_options = ttk.Frame(export_frame)
        format_options.grid(row=1, column=0, columnspan=2, sticky="w")
        
        ttk.Radiobutton(
            format_options,
            text="PNG (Transparent)",
            variable=self.export_format,
            value="png",
            command=self.update_export_format_options
        ).grid(row=0, column=0, sticky="w")
        
        ttk.Radiobutton(
            format_options,
            text="JPG (Compressed)",
            variable=self.export_format,
            value="jpg",
            command=self.update_export_format_options
        ).grid(row=1, column=0, sticky="w")
        
        self.pdf_radio = ttk.Radiobutton(
            format_options,
            text="PDF (Vector)",
            variable=self.export_format,
            value="pdf",
            command=self.update_export_format_options
        )
        self.pdf_radio.grid(row=2, column=0, sticky="w")
        
        # Disable PDF option if reportlab is not available
        if not PDF_AVAILABLE:
            self.pdf_radio.config(state="disabled")
            # Add a note about PDF requirement
            pdf_note = ttk.Label(
                format_options,
                text="(Install reportlab: pip install reportlab)",
                font=('Helvetica', 8),
                foreground="gray"
            )
            pdf_note.grid(row=3, column=0, sticky="w", padx=(20, 0))
        
        # JPG quality setting (only show when JPG is selected)
        self.jpg_quality_frame = ttk.Frame(export_frame)
        self.jpg_quality_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        
        ttk.Label(self.jpg_quality_frame, text="JPG Quality:").pack(side="left", padx=(0, 5))
        self.jpg_quality_scale = ttk.Scale(
            self.jpg_quality_frame,
            from_=50,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.jpg_quality,
            length=100
        )
        self.jpg_quality_scale.pack(side="left", padx=(0, 5))
        ttk.Label(self.jpg_quality_frame, textvariable=self.jpg_quality).pack(side="left")
        
        # Initially hide JPG quality settings
        self.jpg_quality_frame.grid_remove()
        self.update_export_format_options()
        
        # Info text about valid characters
        valid_chars_frame = ttk.Frame(content, padding=5)
        valid_chars_frame.pack(fill="x", pady=5)
        
        valid_chars_label = ttk.Label(
            valid_chars_frame, 
            text="Valid characters: a-z, A-Z, 0-9, space,\nand )(#\"?'.-.:;",
            justify="left"
        )
        valid_chars_label.pack(anchor="w")
        
    def create_background_section(self, parent):
        # Background Section
        self.background_frame = ModernFrame(parent, "Background Options")
        self.background_frame.pack(fill="x", pady=(0, 15))
        
        # Add content to the frame
        content = self.background_frame.content_frame
        
        # Background type selection
        ttk.Label(content, text="Background Type:").pack(anchor="w", pady=(0, 5))
        
        # Background options
        bg_options_frame = ttk.Frame(content)
        bg_options_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Radiobutton(
            bg_options_frame,
            text="Transparent",
            variable=self.background_type,
            value="transparent"
        ).grid(row=0, column=0, sticky="w")
        
        ttk.Radiobutton(
            bg_options_frame,
            text="White",
            variable=self.background_type,
            value="white"
        ).grid(row=1, column=0, sticky="w")
        
        ttk.Radiobutton(
            bg_options_frame,
            text="Custom Color",
            variable=self.background_type,
            value="color",
            command=self.update_background_options
        ).grid(row=2, column=0, sticky="w")
        
        ttk.Radiobutton(
            bg_options_frame,
            text="Image",
            variable=self.background_type,
            value="image",
            command=self.update_background_options
        ).grid(row=3, column=0, sticky="w")
        
        # Custom background options frame (initially empty)
        self.bg_custom_frame = ttk.Frame(content)
        self.bg_custom_frame.pack(fill="x", pady=5)
        
        # Make sure the background settings match the radio button
        self.update_background_options()
        
    def update_background_options(self):
        """Update the background options based on selection"""
        # Clear existing widgets
        for widget in self.bg_custom_frame.winfo_children():
            widget.destroy()
            
        bg_type = self.background_type.get()
        
        if bg_type == "color":
            # Show color picker option
            color_frame = ttk.Frame(self.bg_custom_frame)
            color_frame.pack(fill="x")
            
            # Color preview
            self.bg_color_preview = tk.Label(
                color_frame, 
                background=self.background_color, 
                width=8, 
                height=2,
                borderwidth=1,
                relief="sunken"
            )
            self.bg_color_preview.pack(side="left", padx=(0, 10))
            
            # Color value
            color_text = ttk.Label(color_frame, text=self.background_color)
            color_text.pack(side="left", padx=(0, 10))
            
            # Pick color button
            color_btn = ttk.Button(
                color_frame, 
                text="Choose Color", 
                command=self.choose_background_color
            )
            color_btn.pack(side="left")
            
        elif bg_type == "image":
            # Show image picker option
            image_frame = ttk.Frame(self.bg_custom_frame)
            image_frame.pack(fill="x")
            
            # Current image path or "No image selected"
            path_text = self.background_image_path if self.background_image_path else "No image selected"
            path_preview = ttk.Label(
                image_frame, 
                text=path_text,
                wraplength=200
            )
            path_preview.pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            # Browse button
            browse_btn = ttk.Button(
                image_frame, 
                text="Browse...", 
                command=self.choose_background_image
            )
            browse_btn.pack(side="right")
            
            # Show image preview if available
            if self.background_image_path and os.path.exists(self.background_image_path):
                try:
                    # Try to load and display a small preview
                    img = Image.open(self.background_image_path)
                    img.thumbnail((150, 100))  # Resize to thumbnail
                    photo = ImageTk.PhotoImage(img)
                    
                    preview_frame = ttk.Frame(self.bg_custom_frame, padding=5)
                    preview_frame.pack(fill="x", pady=5)
                    
                    img_preview = ttk.Label(preview_frame, image=photo)
                    img_preview.image = photo  # Keep a reference
                    img_preview.pack()
                except Exception as e:
                    print(f"Error loading image preview: {e}")
    
    def choose_background_color(self):
        """Open color picker for background color"""
        color = askcolor(self.background_color, self.root)[1]
        if color:
            self.background_color = color
            self.update_background_options()  # Refresh the display
    
    def choose_background_image(self):
        """Open file dialog to choose background image"""
        filetypes = [
            ("Image Files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
            ("All Files", "*.*")
        ]
        
        file_path = filedialog.askopenfilename(
            title="Select Background Image",
            filetypes=filetypes
        )
        
        if file_path:
            self.background_image_path = file_path
            self.update_background_options()  # Refresh the display
            
    def create_queue_section(self, parent):
        # Text Queue Section
        self.queue_frame = ModernFrame(parent, "Text Queue")
        self.queue_frame.pack(fill="x", expand=True)
        
        # Add content to the frame
        content = self.queue_frame.content_frame
        
        # Queue list with scrollbar
        queue_list_frame = ttk.Frame(content)
        queue_list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Create Listbox with scrollbar
        self.queue_listbox = tk.Listbox(queue_list_frame, height=6, selectmode=tk.SINGLE)
        self.queue_listbox.pack(side="left", fill="both", expand=True)
        
        queue_scrollbar = ttk.Scrollbar(queue_list_frame)
        queue_scrollbar.pack(side="right", fill="y")
        
        self.queue_listbox.config(yscrollcommand=queue_scrollbar.set)
        queue_scrollbar.config(command=self.queue_listbox.yview)
        
        # Queue control buttons
        queue_buttons_frame = ttk.Frame(content)
        queue_buttons_frame.pack(fill="x", pady=(0, 5))
        
        # Add to queue button
        self.add_to_queue_btn = ttk.Button(
            queue_buttons_frame,
            text="Add to Queue",
            command=self.add_to_queue
        )
        self.add_to_queue_btn.pack(side="left", padx=5)
        
        # Remove from queue button
        self.remove_from_queue_btn = ttk.Button(
            queue_buttons_frame,
            text="Remove Selected",
            command=self.remove_from_queue
        )
        self.remove_from_queue_btn.pack(side="left", padx=5)
        
        # Clear queue button
        self.clear_queue_btn = ttk.Button(
            queue_buttons_frame,
            text="Clear Queue",
            command=self.clear_queue
        )
        self.clear_queue_btn.pack(side="left", padx=5)
        
        # Process queue button (bottom)
        self.process_queue_btn = ttk.Button(
            content,
            text="Process Queue",
            style='Accent.TButton',
            command=self.process_queue
        )
        self.process_queue_btn.pack(anchor="center", pady=10, ipadx=10, ipady=5)
        self.process_queue_btn.config(state="disabled")  # Initially disabled

    def update_legibility_value(self, *args):
        """Update the legibility value display when slider is moved"""
        value = int(float(self.legibilityscale.get()))
        self.legibility_value.set(str(value))
        self._queue_mini_preview()
        
    def update_stroke_width_value(self, *args):
        """Update the stroke width value display when slider is moved"""
        value = float(self.widthscale.get())
        self.stroke_width_value.set(f"{value:.1f}")
        self._queue_mini_preview()
        
    def update_line_width_value(self, *args):
        """Update the line width value display and entry field when slider is moved"""
        value = int(float(self.linewidthscale.get()))
        self.line_width_value.set(str(value))
        self.custom_width_var.set(str(value))
        
    def update_line_spacing_value(self, *args):
        """Update the line spacing value display when slider is moved"""
        value = int(float(self.lineheightscale.get()))
        self.line_spacing_value.set(str(value))

    def create_text_input_section(self, parent):
        # Input text area with title
        input_frame = ModernFrame(parent, "Your Text")
        input_frame.pack(fill="both", expand=True)
        
        content = input_frame.content_frame
        
        # Create text input with scrollbar in a frame
        text_frame = ttk.Frame(content)
        text_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.inputtext = tk.Text(text_frame, wrap="word", borderwidth=2, relief="sunken")
        self.inputtext.pack(side="left", fill="both", expand=True)
        
        scroll = ttk.Scrollbar(text_frame)
        scroll.pack(side="right", fill="y")
        
        self.inputtext.configure(yscrollcommand=scroll.set)
        scroll.config(command=self.inputtext.yview)
        
        # Name entry for the queue
        name_frame = ttk.Frame(content)
        name_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(name_frame, text="Text Name (optional):").pack(side="left", padx=(0, 5))
        self.text_name_var = tk.StringVar()
        self.text_name_entry = ttk.Entry(name_frame, width=30, textvariable=self.text_name_var)
        self.text_name_entry.pack(side="left", fill="x", expand=True)
        
        # Generate button at the bottom
        self.generate_frame = ttk.Frame(content)
        self.generate_frame.pack(fill="x", pady=10)
        
        self.generatebutton = ttk.Button(
            self.generate_frame, 
            text='Generate Writing!', 
            style='Accent.TButton',  # Use an accent style if available
            command=lambda: self.generate_dialog(parent.winfo_toplevel())
        )
        self.generatebutton.pack(anchor="center", ipadx=20, ipady=10)
        
        # Configure invalid character highlighting
        self.inputtext.tag_config('invalid', background='#442222', foreground='white')
        self.inputtext.bind("<KeyRelease>", lambda e: self._highlight_invalid())
        self.inputtext.bind("<KeyRelease>", lambda e: self._queue_mini_preview(), add="+")

    def _highlight_invalid(self, event=None):
        if self.auto_remove_invalid.get():
            self.inputtext.tag_remove('invalid', "1.0", tk.END)
            return
        # Use 'event' to avoid a separate lambda if needed, but keeping separate is fine
        txt = self.inputtext.get("1.0", "end-1c") # Use end-1c to avoid trailing newline
        self.inputtext.tag_remove('invalid', "1.0", tk.END)
        # mark each invalid char
        for i, char in enumerate(txt):
            if char not in self.valid_chars:
                start_index = f"1.0 + {i} chars"
                end_index = f"1.0 + {i+1} chars"
                self.inputtext.tag_add('invalid', start_index, end_index)

    def get_max_line_width(self):
        """Get the max line width, either from scale or custom entry if larger"""
        try:
            scale_value = round(self.linewidthscale.get())
            custom_value = int(self.custom_width_var.get())
            return max(scale_value, custom_value)
        except (ValueError, tk.TclError):
            # If the custom value is not a valid integer, use the scale value
            return round(self.linewidthscale.get())

    def disallow_closing(self, root):
        #root.destroy()
        return
    
    def add_to_queue(self):
        """Add current text to the queue"""
        text = self.inputtext.get("1.0", tk.END).replace('Q', 'q').replace('X', 'x')
        
        if len("".join(text.split())) == 0:
            messagebox.showerror('No Text!', 'Error: There is no text in the textbox.')
            return
            
        # Check for invalid characters if auto-remove is not enabled
        if not self.auto_remove_invalid.get():
            for letter in text:
                if letter not in self.valid_chars:
                    messagebox.showerror('Invalid Chars!', 'Error: Invalid Symbol Found: \"'+letter+'\"\nValid Symbols: a-z | A-Z | 0-9 | )(#"?\'.-.:;')
                    return
        else:
            # Filter out invalid characters
            filtered_text = ""
            for letter in text:
                if letter in self.valid_chars:
                    filtered_text += letter
            text = filtered_text
            
        # Get the item name (use custom name if provided, otherwise use text preview)
        name = self.text_name_var.get().strip()
        queue_item = QueueItem(text, name)
        
        # Add to internal queue and update listbox
        self.text_queue.append(queue_item)
        display_name = queue_item.name if queue_item.name else f"Text {len(self.text_queue)}"
        self.queue_listbox.insert(tk.END, display_name)
        
        # Enable process queue button if queue has items
        if len(self.text_queue) > 0:
            self.process_queue_btn.config(state="normal")
            
        # Clear the name field
        self.text_name_var.set("")
        
        # Show confirmation
        messagebox.showinfo("Queue Updated", f"Text added to queue. Queue now has {len(self.text_queue)} item(s).")
    
    def remove_from_queue(self):
        """Remove selected item from queue"""
        selected = self.queue_listbox.curselection()
        if not selected:
            messagebox.showinfo("Selection Required", "Please select an item from the queue to remove.")
            return
            
        index = selected[0]
        self.queue_listbox.delete(index)
        self.text_queue.pop(index)
        
        # Disable process queue button if queue is empty
        if len(self.text_queue) == 0:
            self.process_queue_btn.config(state="disabled")
    
    def clear_queue(self):
        """Clear the entire queue"""
        if len(self.text_queue) == 0:
            return
            
        confirm = messagebox.askyesno("Clear Queue", "Are you sure you want to clear the entire queue?")
        if confirm:
            self.queue_listbox.delete(0, tk.END)
            self.text_queue = []
            self.process_queue_btn.config(state="disabled")
    
    def process_queue(self):
        """Start processing all items in the queue"""
        if len(self.text_queue) == 0:
            messagebox.showinfo("Empty Queue", "The queue is empty. Please add items to the queue first.")
            return
            
        self.processing_queue = True
        self.current_queue_index = 0
        
        # Disable buttons during queue processing
        self.disable_controls()
        
        # Start processing the first item
        self.process_next_queue_item()
    
    def process_next_queue_item(self):
        """Process the next item in the queue"""
        if self.current_queue_index >= len(self.text_queue):
            # Queue is complete
            self.processing_queue = False
            self.enable_controls()
            messagebox.showinfo("Queue Complete", "All items in the queue have been processed.")
            return
            
        # Get the next item from the queue
        queue_item = self.text_queue[self.current_queue_index]
        self.text = queue_item.text
        
        # Highlight the current item in the queue listbox
        self.queue_listbox.selection_clear(0, tk.END)
        self.queue_listbox.selection_set(self.current_queue_index)
        self.queue_listbox.see(self.current_queue_index)
        
        # Start the generation dialog for this item
        self.generate_dialog(self.root, is_queue_item=True) 
    
    def disable_controls(self):
        """Disable controls during queue processing"""
        self.generatebutton.config(state="disabled")
        self.add_to_queue_btn.config(state="disabled")
        self.remove_from_queue_btn.config(state="disabled")
        self.clear_queue_btn.config(state="disabled")
        self.process_queue_btn.config(state="disabled")
    
    def enable_controls(self):
        """Re-enable controls after queue processing"""
        self.generatebutton.config(state="normal")
        self.add_to_queue_btn.config(state="normal")
        self.remove_from_queue_btn.config(state="normal")
        self.clear_queue_btn.config(state="normal")
        if len(self.text_queue) > 0:
            self.process_queue_btn.config(state="normal")
    
    def _show_errors(self):
        if not self._errors:
            messagebox.showinfo("Log", "No errors recorded.")
            return
        w = tk.Toplevel(self.root)
        w.title("Generation Log")
        w.geometry("600x300")
        txt = tk.Text(w, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", "\n".join(self._errors))
        txt.config(state="disabled")

    def generate_dialog(self, win, is_queue_item=False):
        # Reset cancel flag and error list
        self._cancel = False
        self._errors = []
        
        if not is_queue_item:
            self.generatebutton.config(state='disabled')
            self.text = self.inputtext.get("1.0", tk.END).replace('Q', 'q').replace('X', 'x')

            if len("".join(self.text.split())) == 0:
                messagebox.showerror('No Text!', 'Error: There is no text in the textbox.')
                self.generatebutton.config(state='normal')
                return
            
            # Handle invalid characters according to user preference
            if self.auto_remove_invalid.get():
                # Auto-remove invalid characters
                filtered_text = ""
                removed_chars = set()
                for letter in self.text:
                    if letter in self.valid_chars:
                        filtered_text += letter
                    else:
                        removed_chars.add(letter)
                
                self.text = filtered_text
                
                # Inform user about removed characters if any were removed
                if removed_chars:
                    removed_chars_str = ", ".join([f'"{c}"' for c in removed_chars])
                    messagebox.showinfo('Characters Removed', f'The following invalid characters were removed: {removed_chars_str}')
                    
                # Update the text in the textbox
                self.inputtext.delete("1.0", tk.END)
                self.inputtext.insert("1.0", self.text)
                
            else:
                # Original behavior - check for invalid characters and show error
                char_array = list(self.text)
                for letter in char_array:
                    if not letter in self.valid_chars:
                        messagebox.showerror('Invalid Chars!', 'Error: Invalid Symbol Found: \"'+letter+'\"\nValid Symbols: a-z | A-Z | 0-9 | )(#"?\'.-.:;')
                        self.generatebutton.config(state='normal')
                        return
        
        # Set dialog title based on whether we're processing a queue item
        dialog_title = "Generating Writing!"
        if is_queue_item:
            current_item = self.text_queue[self.current_queue_index]
            item_name = current_item.name if current_item.name else f"Text {self.current_queue_index + 1}"
            dialog_title = f"Generating Item {self.current_queue_index + 1} of {len(self.text_queue)}: {item_name}"
        
        self.generatedialog = tk.Toplevel(win)
        self.generatedialog.geometry("550x170")
        self.generatedialog.iconbitmap(resourcepath('gui/icon.ico'))
        self.generatedialog.title(dialog_title)
        self.generatedialog.resizable(0, 0)
        self.generatedialog.protocol("WM_DELETE_WINDOW", lambda: self.disallow_closing(self.generatedialog))
        
        # Make dialog look nice
        dialog_frame = ttk.Frame(self.generatedialog, padding=20)
        dialog_frame.pack(fill="both", expand=True)
        
        if is_queue_item:
            queue_status = ttk.Label(dialog_frame, text=f"Processing queue item {self.current_queue_index + 1} of {len(self.text_queue)}")
            queue_status.pack(pady=(0, 5))
        
        title_label = ttk.Label(dialog_frame, text="Generating Your Handwriting", font=("Helvetica", 14, "bold"))
        title_label.pack(pady=(0, 15))
        
        self.progress = ttk.Progressbar(dialog_frame)
        self.progress.pack(fill="x", pady=(0, 10))
        
        self.generatelabel = ttk.Label(dialog_frame, text='Initializing Hand')
        self.generatelabel.pack()
        
        btns = ttk.Frame(dialog_frame)
        btns.pack(pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=lambda: setattr(self, "_cancel", True)).pack(side="left", padx=5)
        
        self._log_btn = ttk.Button(btns, text="View log", command=self._show_errors)
        self._log_btn.pack(side="left", padx=5)
        self._log_btn.pack_forget()

        t = Thread(target=lambda: self.generate_writing(is_queue_item))
        t.setDaemon(True)
        t.start()
            
    def split_string(self, text, length) -> list:
        return textwrap.wrap(text, length)
   
    def generate_writing(self, is_queue_item=False):
        def bail_out():
            try:
                shutil.rmtree(self.tempdir, ignore_errors=True)
            except Exception:
                pass
            if hasattr(self, "generatedialog") and self.generatedialog.winfo_exists():
                self.ui(self.generatedialog.destroy)
            # If we were batch-processing, re-enable controls
            if not is_queue_item:
                self.ui(self.generatebutton.config, state='normal')
            else:
                 self.enable_controls()

        if not self.hand:
            self.hand = Hand()
        self.ui(self.step_bar_after, self.progress, 10.0)
        
        if self._cancel: bail_out(); return

        self.ui(self.generatelabel.config, text='Preparing Lines')
        
        bias = math.sqrt(self.legibilityscale.get()/100)
        width = self.widthscale.get()/4 + 0.6
        
        lines = self.text.splitlines()
        
        fileid = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        self.tempdir = resourcepath(f'handsynth-temp-{fileid}')
        os.makedirs(self.tempdir, exist_ok=True)
        
        synthesized_lines = []
        max_width = self.get_max_line_width()
        
        for line in lines:
            if len(line) > max_width:
                sublines = self.split_string(line, max_width)
                for subline in sublines:
                    synthesized_lines.append(subline)
            else:
                synthesized_lines.append(line if line else ' ')
                
        proglength = 60/len(synthesized_lines)
        time.sleep(0.5)
        self.ui(self.step_bar_after, self.progress, 5.0)
        
        start_t = time.time()
        for i, line in enumerate(synthesized_lines):
            if self._cancel: bail_out(); return
            
            avg = (time.time() - start_t) / max(1, i)
            remain = avg * (len(synthesized_lines) - i)
            self.ui(self.generatelabel.config,
                    text=f'Synthesizing Lines ({i+1}/{len(synthesized_lines)}) — ETA ~{int(remain)}s')
            
            try:
                self.hand.write(
                    filename=os.path.join(self.tempdir, f'{i}.svg'),
                    lines=[line],
                    biases=[bias],
                    styles=[self.currentstyle],
                    stroke_colors=[self.stroke_color],
                    stroke_widths=[width],
                )
            except Exception as e:
                self._errors.append(f"Synthesize line {i+1}: {e}")
            
            self.ui(self.step_bar_after, self.progress, proglength)
            
        self.ui(self.generatelabel.config, text='Rasterizing Lines')
        proglength = 20/len(synthesized_lines)
        
        start_r = time.time()
        for i in range(len(synthesized_lines)):
            if self._cancel: bail_out(); return

            avg = (time.time() - start_r) / max(1, i)
            remain = avg * (len(synthesized_lines) - i)
            self.ui(self.generatelabel.config,
                    text=f'Rasterizing ({i+1}/{len(synthesized_lines)}) — ETA ~{int(remain)}s')

            try:
                if synthesized_lines[i] == ' ':
                    Image.new('RGBA',(2_000 ,120)).save(os.path.join(self.tempdir, f'{i}.png'))
                else:
                    svg2png(os.path.join(self.tempdir, f'{i}.svg'), os.path.join(self.tempdir, f'{i}.png'))
            except Exception as e:
                 self._errors.append(f"Rasterize line {i+1}: {e}")
            self.ui(self.step_bar_after, self.progress, proglength)
        
        if self._cancel: bail_out(); return

        line_spacing = round(self.lineheightscale.get()) 
        
        self.ui(self.generatelabel.config, text='Combining Lines')
        
        canvas = Image.new('RGBA', (2_400, 400+round(line_spacing*len(synthesized_lines))))
        
        use_image_placement = self.image_enabled.get()
        image_bounds = None
        
        if use_image_placement and self.image_path and os.path.exists(self.image_path):
            try:
                with Image.open(self.image_path) as placed_image:
                    placed_image = placed_image.resize((self.image_width.get(), self.image_height.get()))
                    img_x, img_y = self.image_x.get(), self.image_y.get()
                    img_width, img_height = self.image_width.get(), self.image_height.get()
                    image_bounds = (img_x, img_y, img_x + img_width, img_y + img_height)
                    if placed_image.mode != 'RGBA':
                        placed_image = placed_image.convert('RGBA')
                    canvas.paste(placed_image, (img_x, img_y), placed_image)
            except Exception as e:
                self._errors.append(f"Image placement: {e}")
                image_bounds = None
        
        for i in range(len(synthesized_lines)):
            with Image.open(os.path.join(self.tempdir, f'{i}.png')) as line_image:
                y_pos = line_spacing * (i + 1)
                x_pos = 400
                if self.orientation.get() == 'Right': x_pos = 2_000 - line_image.width
                elif self.orientation.get() == 'Middle': x_pos = 1_000 - (line_image.width / 2)
                
                if image_bounds and use_image_placement:
                    img_left, img_top, img_right, img_bottom = image_bounds
                    if (img_top <= y_pos + line_image.height and y_pos <= img_bottom):
                        wrap_style = self.image_wrap_style.get()
                        if (x_pos < img_right and x_pos + line_image.width > img_left):
                            if wrap_style == "left":
                                x_pos = img_left - line_image.width - 20
                            elif wrap_style == "right":
                                x_pos = img_right + 20
                            else: # both
                                if (img_left > 2000 - img_right): x_pos = img_left - line_image.width - 20
                                else: x_pos = img_right + 20
                canvas.paste(line_image, (int(x_pos), int(y_pos)), line_image)
        
        if self._cancel: bail_out(); return

        canvas = fulltrim(canvas)
        finalcanvas = Image.new('RGBA', (canvas.width+120, canvas.height+120))
        finalcanvas.paste(canvas, (60, 60))
        
        file_suffix = ""
        if is_queue_item:
            item_name = self.text_queue[self.current_queue_index].name
            safe_name = "".join([c for c in item_name if c.isalnum() or c in "-_ "]) if item_name else ""
            file_suffix = f"-{safe_name}" if safe_name else f"-queue-{self.current_queue_index + 1}"
        
        if not os.path.isdir('outputs'): os.mkdir('outputs')
        output_path = f'outputs/{fileid}{file_suffix}'
        
        bg_type = self.background_type.get()
        export_format = self.export_format.get()
        final_output = finalcanvas
        
        if bg_type != "transparent":
            bg_color = 'white' if bg_type == 'white' else self.background_color
            background = Image.new('RGB', finalcanvas.size, color=bg_color)
            if bg_type == "image" and self.background_image_path:
                try:
                    bg_img = Image.open(self.background_image_path).resize(finalcanvas.size)
                    if bg_img.mode != 'RGB': bg_img = bg_img.convert('RGB')
                    background = bg_img
                except Exception as e:
                     self._errors.append(f"Background image: {e}")
            background.paste(finalcanvas, (0, 0), finalcanvas)
            final_output = background
        
        output_files = []
        try:
            if export_format == "png":
                final_output.save(f'{output_path}.png')
                output_files.append(f'{output_path}.png')
            elif export_format == "jpg":
                self.create_jpg(final_output, f'{output_path}.jpg', self.jpg_quality.get())
                output_files.append(f'{output_path}.jpg')
            elif export_format == "pdf" and PDF_AVAILABLE:
                self.create_pdf(final_output, f'{output_path}.pdf')
                output_files.append(f'{output_path}.pdf')
        except Exception as e:
            self._errors.append(f"Saving output file: {e}")

        self.ui(self.step_bar_after, self.progress, 4.9)
        
        self.preview_info = {
            'show_preview': not is_queue_item or self.current_queue_index == len(self.text_queue) - 1,
            'output_files': output_files,
            'final_output': final_output,
            'export_format': export_format
        }
        
        shutil.rmtree(self.tempdir, ignore_errors=True)
        time.sleep(.2)
        
        if self._errors and hasattr(self, "_log_btn"):
            self.ui(self._log_btn.pack, side="left", padx=5)
            self.ui(self.generatelabel.config, text="Finished with warnings. Open log for details.")
        else:
            if hasattr(self, "generatedialog"):
                self.ui(self.generatedialog.destroy)
        
        self.ui(self.show_preview_after_dialog)
        
        if is_queue_item:
            self.current_queue_index += 1
            if self.current_queue_index < len(self.text_queue):
                time.sleep(0.5)
                self.process_next_queue_item()
            else:
                self.processing_queue = False
                self.enable_controls()
                if not self._errors:
                    self.ui(messagebox.showinfo, "Queue Complete", "All items processed.")
        else:
            self.ui(self.generatebutton.config, state='normal')
    
    def show_file(self, file_path):
        try:
            if os.name == "nt": subprocess.Popen(f'explorer /select,"{file_path}"')
            else: subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", os.path.dirname(file_path)])
        except Exception as e:
            print(f"Could not open file location: {e}")

    def choose_color(self, win, usercolor=True):
        if usercolor:
            colorpickercolor = askcolor(self.stroke_color, win)[1]
            if colorpickercolor:
                self.stroke_color = colorpickercolor
            else:
                return
        
        if hasattr(self, 'color_display_frame'):
            for widget in self.color_display_frame.winfo_children(): widget.destroy()
            color_sample = tk.Canvas(self.color_display_frame, width=150, height=30, background=self.stroke_color, borderwidth=1, relief="sunken")
            color_sample.pack(pady=5)
            ttk.Label(self.color_display_frame, text=self.stroke_color).pack()
        self._queue_mini_preview()
        
    def set_style(self, win, styleindex, stylebook=None):
        self.currentstyle = styleindex
        if hasattr(self, 'style_preview_frame'):
            for widget in self.style_preview_frame.winfo_children(): widget.destroy()
            styleimage = self.style_images_cache.get(styleindex) or ImageTk.PhotoImage(self.styles[styleindex])
            self.style_images_cache[styleindex] = styleimage
            style_label = ttk.Label(self.style_preview_frame, image=styleimage)
            style_label.image = styleimage
            style_label.pack()
            ttk.Label(self.style_preview_frame, text=f"Style {styleindex + 1}").pack()
        if stylebook and stylebook.winfo_exists(): stylebook.withdraw()
        self._queue_mini_preview()
            
    def open_stylebook(self, win):
        if getattr(self, "_stylebook", None) and self._stylebook.winfo_exists():
            self._stylebook.deiconify(); self._stylebook.lift(); return

        sb = tk.Toplevel(win)
        self._stylebook = sb
        sb.withdraw()
        sb.title("Select Writing Style")
        try: sb.iconbitmap(resourcepath('gui/icon.ico'))
        except Exception: pass
        sb.resizable(0, 0); sb.transient(win); sb.grab_set()

        main_frame = ttk.Frame(sb, padding=10)
        main_frame.pack(fill="both", expand=True)
        ttk.Label(main_frame, text="Choose Your Writing Style", font=("Helvetica", 14, "bold")).pack(pady=(0, 10))

        grid = ttk.Frame(main_frame)
        grid.pack(fill="both", expand=True)

        self._populate_style_tiles(grid, batch=4)

        sb.update_idletasks()
        px, py, pw, ph = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
        sw, sh = sb.winfo_width(), sb.winfo_height()
        x, y = px + max(0, (pw - sw) // 2), py + max(0, (ph - sh) // 2)
        sb.geometry(f"+{x}+{y}")
        sb.deiconify(); sb.lift()

    def _populate_style_tiles(self, parent, start=0, batch=4):
        end = min(start + batch, 12)
        for i in range(start, end):
            row, col = divmod(i, 3)
            tile = ttk.Frame(parent, borderwidth=2, relief="raised", padding=5)
            tile.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            styleimage = self.style_images_cache.get(i)
            lbl = ttk.Label(tile, image=styleimage)
            lbl.image = styleimage; lbl.pack(pady=(0, 5))
            ttk.Label(tile, text=f"Style {i + 1}").pack()
            
            def choose(idx=i):
                self.set_style(self.root, idx, None)
                if getattr(self, "_stylebook", None) and self._stylebook.winfo_exists():
                    self._stylebook.withdraw()

            ttk.Button(tile, text="Select", command=choose).pack(pady=(5, 0))

        for c in range(3): parent.grid_columnconfigure(c, weight=1)
        if end < 12: parent.after(1, lambda: self._populate_style_tiles(parent, start=end, batch=batch))

    def _queue_mini_preview(self):
        if self._mini_prev_after:
            self.root.after_cancel(self._mini_prev_after)
        self._mini_prev_after = self.root.after(250, self._render_mini_preview)

    def _render_mini_preview(self):
        tempdir = None
        try:
            text = self.inputtext.get("1.0", "1.end")
            if not text.strip(): text = "The quick brown fox"
            sample = text.splitlines()[0] if "\n" in text else text[:40]
            bias = math.sqrt(self.legibilityscale.get()/100)
            width = self.widthscale.get()/4 + 0.6

            fileid = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            tempdir = resourcepath(f'preview-temp-{fileid}')
            os.makedirs(tempdir, exist_ok=True)
            svg_path = os.path.join(tempdir, 'p.svg')
            png_path = os.path.join(tempdir, 'p.png')

            self.hand = self.hand or Hand()
            self.hand.write(filename=svg_path, lines=[sample], biases=[bias], styles=[self.currentstyle],
                            stroke_colors=[self.stroke_color], stroke_widths=[width])
            svg2png(svg_path, png_path)
            im = Image.open(png_path)
            im.thumbnail((220, 60))
            self._mini_prev_img = ImageTk.PhotoImage(im)
            self.mini_preview_label.config(image=self._mini_prev_img, text="")
        except Exception as e:
            self.mini_preview_label.config(image="", text="Preview Error")
        finally:
            if tempdir:
                shutil.rmtree(tempdir, ignore_errors=True)

# Apply custom styles if available
def apply_modern_styles(root):
    try:
        style = ttk.Style()
        style.configure('Accent.TButton', font=('Helvetica', 12))
        style.configure('TLabel', font=('Helvetica', 10))
        style.configure('TButton', font=('Helvetica', 10))
        style.configure('TCheckbutton', font=('Helvetica', 10))
    except Exception as e:
        print(f"Could not apply custom styles: {e}")

if __name__ == '__main__':
    window = tk.Tk()
    window.configure(bg='white')
    
    try:
        window.call('source', resourcepath('gui/azure/azure.tcl'))
        window.call('set_theme', 'dark')
    except tk.TclError:
        print("Azure theme not available, using default theme")
    
    apply_modern_styles(window)
    
    window.iconbitmap(resourcepath('gui/icon.ico'))
    window.minsize(width=1100, height=600)
    window.resizable(1, 1)
    window.title('Handwriting Synthesis')
    window.geometry("1200x700+10+10")
    window.update_idletasks()
    
    mywin = MyWindow(window)

    def _on_close():
        try:
            mywin.save_prefs()
        finally:
            window.destroy()
    window.protocol("WM_DELETE_WINDOW", _on_close)
    
    window.update_idletasks()
    window.mainloop()