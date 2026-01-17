import json
import os
import subprocess
import sys
import threading
from tkinter import filedialog, messagebox
import ctypes

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD


APP_NAME = "Mixamo Animation Fixer for UE5"
APP_VERSION = "1.0.0"

DEFAULT_WINDOW = {
    "width": 700,
    "height": 810,
    "min_width": 600,
    "min_height": 700,
}

DEFAULT_THEME = {
    "bg_dark": "#0d1117",
    "bg_medium": "#161b22",
    "bg_light": "#21262d",
    "bg_input": "#0d1117",
    "accent": "#58a6ff",
    "accent_hover": "#79b8ff",
    "success": "#238636",
    "success_hover": "#2ea043",
    "success_text": "#ffffff",
    "text_primary": "#e6edf3",
    "text_secondary": "#8b949e",
    "text_muted": "#484f58",
    "border": "#30363d",
    "border_light": "#3d444d",
    "danger": "#f85149",
    "danger_hover": "#da3633",
}


def get_app_dir() -> str:
    """Get directory where the application executable is located."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_bundle_dir() -> str:
    """Get directory where bundled resources are located (for PyInstaller)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def load_config(config_path: str) -> dict:
    """Load config from file, merge with defaults."""
    config = {
        "blender_path": "",
        "output_dir": "",
        "window": DEFAULT_WINDOW.copy(),
        "theme": DEFAULT_THEME.copy(),
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)

            config["blender_path"] = user_config.get("blender_path", "")
            config["output_dir"] = user_config.get("output_dir", "")

            if "window" in user_config:
                config["window"].update(user_config["window"])
            if "theme" in user_config:
                config["theme"].update(user_config["theme"])
        except Exception:
            pass

    return config


def save_config(config_path: str, blender_path: str, output_dir: str) -> None:
    """Save configuration to file."""
    data = {"blender_path": blender_path, "output_dir": output_dir}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def set_dark_titlebar(window) -> None:
    """Set dark title bar for a window on Windows."""
    if sys.platform != "win32":
        return

    window.update()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(ctypes.c_int(1)),
        ctypes.sizeof(ctypes.c_int),
    )

    if result != 0:
        DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int),
        )

    window.withdraw()
    window.deiconify()


class MixamoConverterApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        # Paths
        self.app_dir = get_app_dir()
        self.bundle_dir = get_bundle_dir()
        self.config_path = os.path.join(self.app_dir, "config.json")
        self.worker_script = os.path.join(self.bundle_dir, "worker.py")
        self.icon_path = os.path.join(self.bundle_dir, "logo_inv.ico")
        self.default_output_dir = os.path.join(self.app_dir, "Fixed_Animations")

        # Load config
        config = load_config(self.config_path)
        self.colors = config["theme"]
        self.window_config = config["window"]
        self.blender_path = config["blender_path"]
        self.output_dir = config["output_dir"]

        # State
        self.file_paths: list[str] = []
        self.skeleton_mode = "mixamo"

        # Window setup
        self.title(APP_NAME)
        if os.path.exists(self.icon_path):
            self.iconbitmap(self.icon_path)
        self.geometry(f"{self.window_config['width']}x{self.window_config['height']}")
        self.minsize(self.window_config["min_width"], self.window_config["min_height"])
        self.configure(fg_color=self.colors["bg_dark"])
        self._center_window()

        # Build UI
        self._create_header()
        self._create_blender_section()
        self._create_files_section()
        self._create_output_section()
        self._create_skeleton_mode_section()
        self._create_action_section()
        self._create_log_section()
        self._create_footer()

        # Initialize
        self._init_output_dir()
        self._update_blender_status()
        self._log("Ready. Add Mixamo animations to begin.")

    def _center_window(self) -> None:
        """Center the window on screen."""
        self.update_idletasks()
        w, h = self.window_config["width"], self.window_config["height"]
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _init_output_dir(self) -> None:
        """Initialize output directory."""
        if not self.output_dir or not os.path.exists(self.output_dir):
            self.output_dir = self.default_output_dir
            if not os.path.exists(self.output_dir):
                try:
                    os.makedirs(self.output_dir)
                except Exception:
                    self.output_dir = self.app_dir

        self.lbl_output_path.configure(text=self.output_dir)

    def _create_header(self) -> None:
        """Create header with title and settings button."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(25, 10))

        top_bar = ctk.CTkFrame(header, fg_color="transparent")
        top_bar.pack(fill="x")

        ctk.CTkButton(
            top_bar,
            text="⚙",
            width=32,
            height=32,
            fg_color="transparent",
            hover_color=self.colors["bg_light"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=18),
            command=self._open_config,
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="🎮 Mixamo → UE5",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack()

        ctk.CTkLabel(
            header,
            text="A N I M A T I O N   F I X E R",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(pady=(5, 0))

    def _open_config(self) -> None:
        """Open config.json in default text editor."""
        if not os.path.exists(self.config_path):
            save_config(self.config_path, self.blender_path, self.output_dir)

        os.startfile(self.config_path)

    def _create_blender_section(self) -> None:
        """Create Blender path configuration section."""
        section = ctk.CTkFrame(
            self, fg_color=self.colors["bg_medium"], corner_radius=12
        )
        section.pack(fill="x", padx=25, pady=10)

        inner = ctk.CTkFrame(section, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        self.blender_status_icon = ctk.CTkLabel(
            header_row,
            text="⚠️",
            font=ctk.CTkFont(size=14),
            text_color=self.colors["danger"],
        )
        self.blender_status_icon.pack(side="left", padx=(0, 5))

        ctk.CTkLabel(
            header_row,
            text="Blender Path",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        ctk.CTkLabel(
            header_row,
            text="(5.0.0+)",
            text_color=self.colors["text_muted"],
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(8, 0))

        self.btn_change_blender = ctk.CTkButton(
            header_row,
            text="Select",
            command=self._change_blender_path,
            width=80,
            height=28,
            fg_color=self.colors["bg_light"],
            hover_color=self.colors["border"],
            font=ctk.CTkFont(size=12),
        )
        self.btn_change_blender.pack(side="right")

        self.lbl_blender_path = ctk.CTkLabel(
            inner,
            text="Not configured — click 'Select' to choose Blender executable",
            text_color=self.colors["danger"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.lbl_blender_path.pack(fill="x", pady=(5, 0))

    def _create_files_section(self) -> None:
        """Create file selection section."""
        self.files_section = ctk.CTkFrame(
            self, fg_color=self.colors["bg_medium"], corner_radius=12
        )
        self.files_section.pack(fill="x", padx=25, pady=10)

        inner = ctk.CTkFrame(self.files_section, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        ctk.CTkLabel(
            header_row,
            text="📁 Animation Files",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        self.file_count_label = ctk.CTkLabel(
            header_row,
            text="0 files",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
        )
        self.file_count_label.pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            header_row,
            text="+ Add FBX",
            command=self._select_files,
            width=100,
            height=28,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="right")

        ctk.CTkButton(
            header_row,
            text="Clear All",
            command=self._clear_all_files,
            width=70,
            height=28,
            fg_color="transparent",
            hover_color=self.colors["danger"],
            border_width=1,
            border_color=self.colors["danger"],
            text_color=self.colors["danger"],
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=(0, 8))

        files_container = ctk.CTkFrame(inner, fg_color="transparent", height=150)
        files_container.pack(fill="x", pady=(10, 0))
        files_container.pack_propagate(False)

        self.scroll_files = ctk.CTkScrollableFrame(
            files_container,
            fg_color=self.colors["bg_input"],
            corner_radius=8,
            border_width=1,
            border_color=self.colors["border"],
        )
        self.scroll_files.pack(fill="both", expand=True)

        # Register drag-and-drop
        for widget in [self.scroll_files, self.files_section]:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop_files)

        try:
            self.scroll_files._parent_frame.drop_target_register(DND_FILES)
            self.scroll_files._parent_frame.dnd_bind("<<Drop>>", self._on_drop_files)
        except Exception:
            pass

        self._update_file_list_ui()

    def _create_output_section(self) -> None:
        """Create output folder section."""
        section = ctk.CTkFrame(
            self, fg_color=self.colors["bg_medium"], corner_radius=12
        )
        section.pack(fill="x", padx=25, pady=10)

        inner = ctk.CTkFrame(section, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        ctk.CTkLabel(
            header_row,
            text="📤 Export Destination",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        ctk.CTkButton(
            header_row,
            text="Browse",
            width=80,
            height=28,
            command=self._select_output_folder,
            fg_color=self.colors["bg_light"],
            hover_color=self.colors["border"],
            font=ctk.CTkFont(size=12),
        ).pack(side="right")

        path_row = ctk.CTkFrame(inner, fg_color="transparent")
        path_row.pack(fill="x", pady=(5, 0))

        self.lbl_output_path = ctk.CTkLabel(
            path_row,
            text="...",
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=12),
            anchor="w",
            cursor="hand2",
        )
        self.lbl_output_path.pack(side="left")
        self.lbl_output_path.bind("<Button-1>", self._copy_output_path)

        self.lbl_copied = ctk.CTkLabel(
            path_row,
            text="✓ Copied!",
            text_color=self.colors["success"],
            font=ctk.CTkFont(size=11, weight="bold"),
        )

    def _copy_output_path(self, event=None) -> None:
        """Copy output path to clipboard."""
        if not self.output_dir:
            return

        self.clipboard_clear()
        self.clipboard_append(self.output_dir)
        self._log(f"Copied to clipboard: {self.output_dir}")

        self.lbl_output_path.configure(text_color=self.colors["accent"])
        self.after(
            150,
            lambda: self.lbl_output_path.configure(
                text_color=self.colors["text_secondary"]
            ),
        )

        self.lbl_copied.pack(side="left", padx=(10, 0))
        self.after(1500, lambda: self.lbl_copied.pack_forget())

    def _create_action_section(self) -> None:
        """Create main action button."""
        self.btn_convert = ctk.CTkButton(
            self,
            text="FIX ANIMATIONS",
            command=self._start_conversion,
            height=50,
            fg_color=self.colors["success"],
            hover_color=self.colors["success_hover"],
            text_color=self.colors["success_text"],
            font=ctk.CTkFont(size=18, weight="bold"),
            corner_radius=10,
        )
        self.btn_convert.pack(fill="x", padx=25, pady=15)

    def _create_skeleton_mode_section(self) -> None:
        """Create skeleton mode selector."""
        section = ctk.CTkFrame(
            self, fg_color=self.colors["bg_medium"], corner_radius=12
        )
        section.pack(fill="x", padx=25, pady=10)

        inner = ctk.CTkFrame(section, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row,
            text="🦴 Skeleton Type",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        ctk.CTkButton(
            title_row,
            text="?",
            width=24,
            height=24,
            fg_color=self.colors["bg_light"],
            hover_color=self.colors["border"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=12,
            command=self._show_skeleton_info,
        ).pack(side="right")

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 0))

        self.btn_mixamo = ctk.CTkButton(
            btn_frame,
            text="Mixamo SK",
            command=lambda: self._set_skeleton_mode("mixamo"),
            width=150,
            height=36,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
        )
        self.btn_mixamo.pack(side="left", padx=(0, 10))

        self.btn_ue = ctk.CTkButton(
            btn_frame,
            text="Unreal Engine SK",
            command=lambda: self._set_skeleton_mode("ue5_skm"),
            width=150,
            height=36,
            fg_color=self.colors["bg_light"],
            hover_color=self.colors["border"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=13),
            corner_radius=8,
        )
        self.btn_ue.pack(side="left")

        self.skeleton_hint = ctk.CTkLabel(
            inner,
            text="Y Bot, X Bot, etc. Any skeleton from Mixamo",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_muted"],
            anchor="w",
        )
        self.skeleton_hint.pack(fill="x", pady=(8, 0))

    def _show_skeleton_info(self) -> None:
        """Show skeleton type documentation popup."""
        popup = ctk.CTkToplevel(self)
        popup.title("Skeleton Types")
        popup.geometry("550x780")
        popup.minsize(400, 400)
        popup.configure(fg_color=self.colors["bg_dark"])

        if sys.platform == "win32":
            popup.after(100, lambda: set_dark_titlebar(popup))
            if os.path.exists(self.icon_path):
                popup.after(200, lambda: popup.wm_iconbitmap(self.icon_path))

        popup.transient(self)
        self.update_idletasks()

        x = self.winfo_x() + (self.winfo_width() // 2) - 275
        y = self.winfo_y() + (self.winfo_height() // 2) - 325
        popup.geometry(f"550x780+{x}+{y}")

        ctk.CTkLabel(
            popup,
            text="🦴 Skeleton Types Guide",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(pady=(20, 15))

        doc_textbox = ctk.CTkTextbox(
            popup,
            fg_color=self.colors["bg_medium"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=12),
            corner_radius=10,
            wrap="word",
        )
        doc_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # Configure tags
        tb = doc_textbox._textbox
        tb.tag_configure(
            "h1",
            font=ctk.CTkFont(size=16, weight="bold"),
            foreground=self.colors["accent"],
        )
        tb.tag_configure(
            "h2",
            font=ctk.CTkFont(size=13, weight="bold"),
            foreground=self.colors["text_primary"],
        )
        tb.tag_configure(
            "normal",
            font=ctk.CTkFont(size=12),
            foreground=self.colors["text_secondary"],
        )
        tb.tag_configure(
            "numbered",
            font=ctk.CTkFont(size=12),
            foreground=self.colors["text_secondary"],
            lmargin1=20,
            lmargin2=35,
        )

        step_counter = [0]

        def h1(text):
            tb.insert("end", text + "\n\n", "h1")

        def h2(text):
            step_counter[0] = 0
            tb.insert("end", text + "\n", "h2")

        def text(t):
            tb.insert("end", t + "\n", "normal")

        def step(t):
            step_counter[0] += 1
            tb.insert("end", f"{step_counter[0]}) {t}\n", "numbered")

        def spacer():
            tb.insert("end", "\n", "normal")

        # Mixamo section
        h1("Mixamo SK")
        text("Skeleton downloaded from Mixamo (Y Bot, X Bot, etc.).")
        text("This works for any skeleton without a root bone and with a Hips bone.")
        spacer()

        h2("What the code does:")
        spacer()
        step("Finds the Hips bone")
        step("Collects world positions of Hips for each frame")
        step("Transfers XY motion from Hips to the Armature object (root motion)")
        step("Removes XY from the Hips bone — keeps only Z")
        step("Renames the top-level object to root")
        spacer()

        h2("How to get animations:")
        spacer()
        text('Go to Mixamo and download the animation "With Skin",')
        text("without uploading a skeleton at all, or use any Mixamo skeleton. Just don't use a skeleton with a root bone (Manny / Quinn / etc).")
        spacer()

        # UE section
        h1("Unreal Engine SK")
        text("Skeleton from Unreal Engine (Quinn, Manny, etc.).")
        text("Has root and pelvis bones in the hierarchy.")
        spacer()

        text("When uploaded to Mixamo, the animation is applied to the object,")
        text("leaving root and pelvis without movement.")
        text("The resulting animation is usually closer to the original Mixamo animation.")
        spacer()

        h2("What the code does:")
        spacer()
        step("Creates a duplicate armature as a data source")
        step("Removes animation from the Armature object")
        step("Creates an Empty that copies the XY position of the pelvis")
        step("Sets up constraints: root → Empty, children → duplicate")
        step("Bakes animation into keyframes")
        step("Removes temporary objects")
        spacer()

        h2("How to get animations:")
        spacer()
        text("Export the Quinn/Manny skeleton from UE,")
        text("upload to Mixamo for auto-rigging,")
        text('download the animation "Without Skin", and after this app fixes it, import it back to UE, choosing your original skeleton as the skeletal mesh.')

        doc_textbox.configure(state="disabled")

        ctk.CTkButton(
            popup,
            text="Close",
            command=popup.destroy,
            width=100,
            height=32,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(size=13),
        ).pack(pady=(0, 20))

    def _set_skeleton_mode(self, mode: str) -> None:
        """Set skeleton processing mode."""
        self.skeleton_mode = mode

        is_mixamo = mode == "mixamo"

        self.btn_mixamo.configure(
            fg_color=self.colors["accent"] if is_mixamo else self.colors["bg_light"],
            hover_color=(
                self.colors["accent_hover"] if is_mixamo else self.colors["border"]
            ),
            text_color=(
                self.colors["success_text"]
                if is_mixamo
                else self.colors["text_secondary"]
            ),
            font=ctk.CTkFont(size=13, weight="bold" if is_mixamo else "normal"),
        )

        self.btn_ue.configure(
            fg_color=self.colors["bg_light"] if is_mixamo else self.colors["accent"],
            hover_color=(
                self.colors["border"] if is_mixamo else self.colors["accent_hover"]
            ),
            text_color=(
                self.colors["text_secondary"]
                if is_mixamo
                else self.colors["success_text"]
            ),
            font=ctk.CTkFont(size=13, weight="normal" if is_mixamo else "bold"),
        )

        hint_text = (
            "Y Bot, X Bot, etc. Any skeleton from Mixamo"
            if is_mixamo
            else "Quinn, Manny, etc. UE skeleton with root bone"
        )
        self.skeleton_hint.configure(text=hint_text)

    def _create_log_section(self) -> None:
        """Create log output section."""
        section = ctk.CTkFrame(
            self, fg_color=self.colors["bg_medium"], corner_radius=12
        )
        section.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        header = ctk.CTkFrame(section, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 5))

        ctk.CTkLabel(
            header,
            text="📋 Log",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Clear",
            width=60,
            height=24,
            command=self._clear_log,
            fg_color="transparent",
            hover_color=self.colors["bg_light"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=11),
        ).pack(side="right")

        ctk.CTkButton(
            header,
            text="Copy",
            width=60,
            height=24,
            command=self._copy_log,
            fg_color="transparent",
            hover_color=self.colors["bg_light"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=(0, 5))

        self.textbox_log = ctk.CTkTextbox(
            section,
            fg_color=self.colors["bg_input"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
            border_width=1,
            border_color=self.colors["border"],
            state="disabled",
        )
        self.textbox_log.pack(fill="both", expand=True, padx=15, pady=(0, 12))

    def _create_footer(self) -> None:
        """Create footer with version info."""
        footer = ctk.CTkFrame(self, fg_color="transparent", height=25)
        footer.pack(fill="x", padx=25, pady=(0, 10))

        ctk.CTkLabel(
            footer,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_muted"],
        ).pack(side="right")

    def _update_blender_status(self) -> None:
        """Update Blender path indicator and button state."""
        is_valid = self.blender_path and os.path.exists(self.blender_path)

        if is_valid:
            self.blender_status_icon.configure(
                text="✓", text_color=self.colors["success"]
            )
            self.lbl_blender_path.configure(
                text=self.blender_path, text_color=self.colors["text_secondary"]
            )
            self.btn_change_blender.configure(text="Change")
            self.btn_convert.configure(
                state="normal",
                fg_color=self.colors["success"],
                text_color=self.colors["success_text"],
            )
        else:
            self.blender_status_icon.configure(
                text="⚠️", text_color=self.colors["danger"]
            )
            self.lbl_blender_path.configure(
                text="Not configured — click 'Select' to choose Blender executable",
                text_color=self.colors["danger"],
            )
            self.btn_change_blender.configure(text="Select")
            self.btn_convert.configure(
                state="disabled",
                fg_color=self.colors["bg_light"],
                text_color=self.colors["text_muted"],
            )

    def _change_blender_path(self) -> None:
        """Open dialog to select Blender executable."""
        filetypes = (
            [("Executable", "*.exe")] if os.name == "nt" else [("All files", "*")]
        )

        initial_dir = None
        if self.blender_path:
            parent = os.path.dirname(self.blender_path)
            if os.path.isdir(parent):
                initial_dir = parent

        path = filedialog.askopenfilename(
            title="Select Blender Executable",
            filetypes=filetypes,
            initialdir=initial_dir,
        )

        if path:
            self.blender_path = path
            save_config(self.config_path, self.blender_path, self.output_dir)
            self._update_blender_status()
            self._log(f"Blender path set: {path}")

    def _select_output_folder(self) -> None:
        """Open dialog to select output folder."""
        initial_dir = None
        if self.output_dir:
            if os.path.isdir(self.output_dir):
                initial_dir = self.output_dir
            else:
                parent = os.path.dirname(self.output_dir)
                if os.path.isdir(parent):
                    initial_dir = parent

        path = filedialog.askdirectory(
            title="Select Export Destination", initialdir=initial_dir
        )

        if path:
            self.output_dir = path
            self.lbl_output_path.configure(text=path)
            save_config(self.config_path, self.blender_path, self.output_dir)

    def _select_files(self) -> None:
        """Open dialog to select FBX files."""
        files = filedialog.askopenfilenames(
            title="Select Mixamo Animations",
            filetypes=[("FBX Files", "*.fbx"), ("All files", "*.*")],
        )

        for f in files:
            if f not in self.file_paths:
                self.file_paths.append(f)

        if files:
            self._update_file_list_ui()

    def _on_drop_files(self, event) -> None:
        """Handle files dropped onto the file list area."""
        raw_data = event.data
        files = []

        i = 0
        while i < len(raw_data):
            if raw_data[i] == "{":
                end = raw_data.find("}", i)
                if end != -1:
                    files.append(raw_data[i + 1 : end])
                    i = end + 1
                else:
                    break
            elif raw_data[i] == " ":
                i += 1
            else:
                end = raw_data.find(" ", i)
                if end == -1:
                    files.append(raw_data[i:])
                    break
                else:
                    files.append(raw_data[i:end])
                    i = end + 1

        added = 0
        for f in files:
            if f.lower().endswith(".fbx") and f not in self.file_paths:
                self.file_paths.append(f)
                added += 1

        if added > 0:
            self._update_file_list_ui()
            self._log(f"Added {added} file(s) via drag-and-drop")

    def _remove_file(self, file_path: str) -> None:
        """Remove a file from the queue."""
        if file_path in self.file_paths:
            self.file_paths.remove(file_path)
            self._update_file_list_ui()

    def _clear_all_files(self) -> None:
        """Clear all files from the queue."""
        self.file_paths.clear()
        self._update_file_list_ui()

    def _clear_log(self) -> None:
        """Clear the log textbox."""
        self.textbox_log.configure(state="normal")
        self.textbox_log.delete("1.0", "end")
        self.textbox_log.configure(state="disabled")

    def _copy_log(self) -> None:
        """Copy all log contents to clipboard."""
        content = self.textbox_log.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)

    def _update_file_list_ui(self) -> None:
        """Update the file list display."""
        for widget in self.scroll_files.winfo_children():
            widget.destroy()

        if not self.file_paths:
            empty_label = ctk.CTkLabel(
                self.scroll_files,
                text="Drop or add FBX files here...",
                text_color=self.colors["text_muted"],
                font=ctk.CTkFont(size=12),
            )
            empty_label.pack(fill="both", expand=True, pady=20)

            empty_label.drop_target_register(DND_FILES)
            empty_label.dnd_bind("<<Drop>>", self._on_drop_files)

            self.file_count_label.configure(text="0 files")
            return

        self.file_count_label.configure(text=f"{len(self.file_paths)} file(s)")

        for file_path in self.file_paths:
            row = ctk.CTkFrame(
                self.scroll_files, fg_color=self.colors["bg_medium"], corner_radius=6
            )
            row.pack(fill="x", pady=2, padx=2)

            ctk.CTkButton(
                row,
                text="✕",
                width=28,
                height=28,
                fg_color=self.colors["danger"],
                hover_color=self.colors["danger_hover"],
                font=ctk.CTkFont(size=12),
                corner_radius=6,
                command=lambda p=file_path: self._remove_file(p),
            ).pack(side="right", padx=6, pady=4)

            ctk.CTkLabel(
                row,
                text=os.path.basename(file_path),
                text_color=self.colors["text_primary"],
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(side="left", padx=10, pady=6, fill="x", expand=True)

    def _start_conversion(self) -> None:
        """Start conversion process in a separate thread."""
        if not self.file_paths:
            messagebox.showwarning(
                "No Files Selected",
                "Please add Mixamo animation files to the queue.",
            )
            return

        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except Exception as e:
                messagebox.showerror(
                    "Export Error", f"Unable to create export directory:\n{e}"
                )
                return

        self.btn_convert.configure(
            state="disabled",
            text="⏳ PROCESSING...",
            fg_color=self.colors["bg_light"],
            text_color=self.colors["text_secondary"],
        )

        thread = threading.Thread(target=self._run_conversion, daemon=True)
        thread.start()

    def _run_conversion(self) -> None:
        """Run the conversion process."""
        if not os.path.exists(self.worker_script):
            self._log(f"ERROR: worker.py not found at: {self.worker_script}")
            self._restore_ui()
            return

        total = len(self.file_paths)
        successful = 0

        for i, fbx_path in enumerate(self.file_paths):
            filename = os.path.basename(fbx_path)
            self._log(f"[{i + 1}/{total}] Processing: {filename}...")

            cmd = [
                self.blender_path,
                "-b",
                "-P",
                self.worker_script,
                "--",
                fbx_path,
                self.output_dir,
                self.skeleton_mode,
            ]

            try:
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    startupinfo=startupinfo,
                )

                # Check for errors in stderr
                has_error = result.stderr and (
                    "Error" in result.stderr
                    or "Exception" in result.stderr
                    or "Traceback" in result.stderr
                )

                if result.returncode == 0 and not has_error:
                    self._log(f"✅ Fixed: {filename}")
                    if result.stdout:
                        for line in result.stdout.split("\n"):
                            if any(x in line for x in ["[Info]", "[Step"]):
                                self._log(f"   {line.strip()}")
                    successful += 1
                else:
                    self._log(f"❌ Failed: {filename}")
                    # Log stdout if contains useful info
                    if result.stdout:
                        for line in result.stdout.strip().split("\n"):
                            line = line.strip()
                            if line and not line.startswith("Blender"):
                                self._log(f"   {line}")
                    # Log stderr (errors)
                    if result.stderr:
                        self._log("   --- Error details ---")
                        for line in result.stderr.strip().split("\n"):
                            line = line.strip()
                            if line:
                                self._log(f"   {line}")

            except Exception as e:
                self._log(f"❌ Error: {e}")

        self._log(f"\n{'=' * 40}")
        self._log(f"Completed: {successful}/{total} animations fixed")
        self._log(f"Output: {self.output_dir}")
        self._log(f"{'=' * 40}\n")

        if successful < total:
            self._show_error()
        else:
            self._show_done()

    def _show_done(self) -> None:
        """Show DONE on button and reset after delay."""
        self.btn_convert.configure(
            state="normal",
            text="✓ DONE",
            fg_color=self.colors["success"],
            text_color=self.colors["success_text"],
        )
        self.after(2000, self._restore_ui)

    def _show_error(self) -> None:
        """Show ERROR on button."""
        self.btn_convert.configure(
            state="normal",
            text="✕ ERROR  —  See logs ↓",
            fg_color=self.colors["danger"],
            text_color=self.colors["success_text"],
        )
        self.after(3000, self._restore_ui)

    def _restore_ui(self) -> None:
        """Restore the UI after processing."""

        self.btn_convert.configure(
            state="normal",
            text="FIX ANIMATIONS",
            fg_color=self.colors["success"],
            text_color=self.colors["success_text"],
        )

    def _log(self, message: str) -> None:
        """Add a message to the log."""
        if hasattr(self, "textbox_log") and self.textbox_log.winfo_exists():
            self.textbox_log.configure(state="normal")
            self.textbox_log.insert("end", message + "\n")
            self.textbox_log.see("end")
            self.textbox_log.configure(state="disabled")
        else:
            print(f"[LOG]: {message}")


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = MixamoConverterApp()
    app.mainloop()
