from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from dotenv import dotenv_values

from app.config_manager import (
    apply_env,
    merged_config,
    missing_required_keys,
    user_env_path,
    write_env_file,
)

FIELD_SPECS = [
    ("LLM_PROVIDER", "LLM provider", False),
    ("AZURE_OPENAI_API_KEY", "Azure OpenAI API key", True),
    ("AZURE_OPENAI_ENDPOINT", "Azure legacy/base endpoint (optional)", False),
    ("AZURE_OPENAI_DEPLOYMENT", "Azure chat deployment", False),
    ("AZURE_OPENAI_API_VERSION", "Azure chat API version", False),
    ("AZURE_OPENAI_EMBEDDING_ENDPOINT", "Azure embedding endpoint", False),
    ("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "Azure embedding deployment", False),
    ("AZURE_OPENAI_EMBEDDING_API_VERSION", "Azure embedding API version", False),
    ("OPENAI_API_KEY", "OpenAI API key", True),
    ("OPENAI_MODEL", "OpenAI model", False),
    ("HUGGINGFACEHUB_API_TOKEN", "Hugging Face token", True),
    ("HF_OPENAI_BASE_URL", "HF OpenAI-compatible base URL", False),
    ("HF_MODEL_ID", "HF model ID", False),
    ("SHAREPOINT_TENANT_ID", "SharePoint tenant ID (optional)", False),
    ("SHAREPOINT_CLIENT_ID", "SharePoint client ID (optional)", False),
    ("SHAREPOINT_CLIENT_SECRET", "SharePoint client secret (optional)", True),
]

DEFAULTS = {
    "LLM_PROVIDER": "azure",
    "AZURE_OPENAI_DEPLOYMENT": "gpt-5-nano",
    "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
    "AZURE_OPENAI_EMBEDDING_API_VERSION": "2023-05-15",
    "OPENAI_MODEL": "gpt-5-nano",
    "HF_OPENAI_BASE_URL": "https://router.huggingface.co/v1",
}


class ConfigWizard:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Taxonomy Agent Setup")
        self.root.geometry("860x720")
        self.root.minsize(760, 620)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.cancelled = True

        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Taxonomy Agent first-run setup",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Fill the fields below or import an existing .env file. "
                "Your settings will be saved to your user profile so the app can launch with one click."
            ),
            wraplength=780,
        ).pack(anchor="w", pady=(6, 12))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Import .env file", command=self._import_env).pack(side="left")
        ttk.Button(actions, text="Open config folder", command=self._open_config_folder).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Reset defaults", command=self._reset_defaults).pack(side="left", padx=(8, 0))

        canvas_frame = ttk.Frame(outer)
        canvas_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self.vars: dict[str, tk.StringVar] = {}
        initial = dict(DEFAULTS)
        initial.update(merged_config())

        form = ttk.Frame(scroll_frame)
        form.pack(fill="x", expand=True)
        for row, (key, label, secret) in enumerate(FIELD_SPECS):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            var = tk.StringVar(value=initial.get(key, ""))
            self.vars[key] = var
            if key == "LLM_PROVIDER":
                widget = ttk.Combobox(
                    form,
                    textvariable=var,
                    values=["azure", "openai", "hf_openai_compat"],
                    state="readonly",
                )
            else:
                widget = ttk.Entry(form, textvariable=var, show="*" if secret else "")
            widget.grid(row=row, column=1, sticky="ew", pady=6)
        form.columnconfigure(1, weight=1)

        self.status_var = tk.StringVar(value=f"Config will be stored at: {user_env_path()}")
        ttk.Label(outer, textvariable=self.status_var, wraplength=780).pack(anchor="w", pady=(12, 8))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(8, 0))
        ttk.Button(footer, text="Cancel", command=self._on_close).pack(side="right")
        ttk.Button(footer, text="Save and launch", command=self._save).pack(side="right", padx=(0, 8))

    def _open_config_folder(self) -> None:
        path = user_env_path().parent
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("Config folder", str(path))

    def _reset_defaults(self) -> None:
        for key, var in self.vars.items():
            var.set(DEFAULTS.get(key, ""))
        self.status_var.set("Defaults restored. Fill or import your real values before saving.")

    def _import_env(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select .env file",
            filetypes=[("Env files", ".env"), ("All files", "*.*")],
        )
        if not filename:
            return
        values = {str(k): str(v) for k, v in dotenv_values(filename).items() if k is not None and v is not None}
        for key, var in self.vars.items():
            if key in values:
                var.set(values[key])
        self.status_var.set(f"Imported values from {filename}")

    def _collect(self) -> dict[str, str]:
        values = {key: var.get().strip() for key, var in self.vars.items()}
        values.setdefault("LLM_PROVIDER", "azure")
        return values

    def _save(self) -> None:
        values = self._collect()
        missing = missing_required_keys(values)
        if missing:
            pretty = "\n".join(f"- {key}" for key in missing)
            messagebox.showerror(
                "Missing required fields",
                f"Please fill these required settings before continuing:\n{pretty}",
            )
            return
        write_env_file(values)
        apply_env(values)
        self.cancelled = False
        self.root.destroy()

    def _on_close(self) -> None:
        self.cancelled = True
        self.root.destroy()


def run_config_wizard() -> bool:
    wizard = ConfigWizard()
    wizard.root.mainloop()
    return not wizard.cancelled


if __name__ == "__main__":
    ok = run_config_wizard()
    raise SystemExit(0 if ok else 1)
