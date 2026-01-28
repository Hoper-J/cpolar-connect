"""
Step-style CLI prompts inspired by @clack/prompts

Provides a clean, step-by-step interaction style for CLI applications.
"""

import sys
from getpass import getpass
from typing import Any, Dict, List, Optional

# ANSI color codes
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Step symbols
STEP_PENDING = "○"
STEP_ACTIVE = "◆"
STEP_DONE = "●"
STEP_ERROR = "■"


def _display_width(text: str) -> int:
    """Calculate display width considering CJK characters."""
    width = 0
    for char in text:
        if "\u4e00" <= char <= "\u9fff":  # CJK Unified Ideographs
            width += 2
        elif "\u3400" <= char <= "\u4dbf":  # CJK Extension A
            width += 2
        elif "\uff00" <= char <= "\uffef":  # Fullwidth ASCII
            width += 2
        else:
            width += 1
    return width


class Prompts:
    """Clack-style prompts for Python CLI applications"""

    def __init__(self, skip_confirm: bool = False, quiet: bool = False):
        """
        Initialize prompts.

        Args:
            skip_confirm: If True, skip confirmation prompts and use defaults
            quiet: If True, suppress non-essential output
        """
        self.skip_confirm = skip_confirm
        self.quiet = quiet

    def intro(self, message: str) -> None:
        """Display intro banner"""
        if self.quiet:
            return
        print()
        print(f"{CYAN}┌{RESET} {BOLD}{message}{RESET}")

    def outro(self, message: str) -> None:
        """Display outro message"""
        if self.quiet:
            return
        print(f"{GREEN}└{RESET} {message}")
        print()

    def outro_cancel(self, message: str = "Operation cancelled") -> None:
        """Display cancellation message"""
        if self.quiet:
            return
        print(f"{YELLOW}└{RESET} {message}")
        print()

    def step(self, message: str, status: str = "active") -> None:
        """
        Display a step indicator.

        Args:
            message: Step description
            status: One of 'pending', 'active', 'done', 'error'
        """
        if self.quiet:
            return
        symbols = {
            "pending": f"{DIM}{STEP_PENDING}{RESET}",
            "active": f"{CYAN}{STEP_ACTIVE}{RESET}",
            "done": f"{GREEN}{STEP_DONE}{RESET}",
            "error": f"{RED}{STEP_ERROR}{RESET}",
        }
        symbol = symbols.get(status, symbols["active"])
        print(f"{symbol}  {message}")

    def log(self, message: str) -> None:
        """Log a plain message"""
        if self.quiet:
            return
        print(f"│  {message}")

    def log_info(self, message: str) -> None:
        """Log info message"""
        if self.quiet:
            return
        print(f"│  {message}")

    def log_warn(self, message: str) -> None:
        """Log warning message"""
        print(f"│  {YELLOW}⚠{RESET} {message}")

    def log_error(self, message: str) -> None:
        """Log error message"""
        print(f"│  {RED}✗{RESET} {message}")

    def log_success(self, message: str) -> None:
        """Log success message"""
        if self.quiet:
            return
        print(f"│  {GREEN}✓{RESET} {message}")

    def note(self, message: str, title: Optional[str] = None) -> None:
        """
        Display a note box.

        Args:
            message: Note content (can be multiline)
            title: Optional title for the note
        """
        if self.quiet:
            return
        print("│")
        if title:
            print(f"│  {DIM}─── {title} ───{RESET}")
        for line in message.split("\n"):
            print(f"│  {line}")
        print("│")

    def text(
        self,
        message: str,
        default: str = "",
        required: bool = False,
    ) -> Optional[str]:
        """
        Text input prompt.

        Args:
            message: Prompt message
            default: Default value
            required: If True, empty input is not allowed

        Returns:
            User input or None if cancelled
        """
        hint = f" {DIM}({default}){RESET}" if default else ""
        prompt_str = f"│  {message}{hint}: "

        try:
            result = input(prompt_str).strip()
            if not result and default:
                return default
            if not result and required:
                self.log_warn("This field is required")
                return self.text(message, default, required)
            return result
        except (KeyboardInterrupt, EOFError):
            print()
            return None

    def password(self, message: str) -> Optional[str]:
        """
        Password input prompt (hidden input).

        Args:
            message: Prompt message

        Returns:
            Password or None if cancelled
        """
        try:
            return getpass(f"│  {message}: ")
        except (KeyboardInterrupt, EOFError):
            print()
            return None

    def confirm(self, message: str, default: bool = True) -> bool:
        """
        Confirmation prompt.

        Args:
            message: Prompt message
            default: Default value if user just presses Enter

        Returns:
            True or False
        """
        if self.skip_confirm:
            return default

        hint = "Y/n" if default else "y/N"
        prompt_str = f"│  {message} ({hint}): "

        try:
            result = input(prompt_str).strip().lower()
            if not result:
                return default
            return result in ("y", "yes", "true", "1")
        except (KeyboardInterrupt, EOFError):
            print()
            return default

    def select(
        self,
        message: str,
        choices: List[Dict[str, Any]],
        default: Optional[str] = None,
    ) -> Optional[str]:
        """
        Single selection prompt.

        Args:
            message: Prompt message
            choices: List of dicts with 'value', 'label', and optional 'hint'
            default: Default value

        Returns:
            Selected value or None if cancelled
        """
        print(f"│  {message}")

        for i, choice in enumerate(choices, 1):
            label = choice.get("label", choice.get("value", ""))
            hint = choice.get("hint", "")
            value = choice.get("value", label)
            is_default = value == default

            marker = f"{GREEN}●{RESET}" if is_default else f"{DIM}○{RESET}"
            hint_str = f" {DIM}({hint}){RESET}" if hint else ""
            default_str = f" {DIM}[default]{RESET}" if is_default else ""

            print(f"│    {marker} {i}. {label}{hint_str}{default_str}")

        prompt_str = f"│  Enter number (1-{len(choices)}): "

        try:
            result = input(prompt_str).strip()
            if not result and default:
                return default

            try:
                idx = int(result) - 1
                if 0 <= idx < len(choices):
                    return choices[idx].get("value", choices[idx].get("label"))
            except ValueError:
                pass

            self.log_warn(f"Please enter a number between 1 and {len(choices)}")
            return self.select(message, choices, default)

        except (KeyboardInterrupt, EOFError):
            print()
            return None

    def multiselect(
        self,
        message: str,
        choices: List[Dict[str, Any]],
        initial: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """
        Multi-selection prompt.

        Args:
            message: Prompt message
            choices: List of dicts with 'value', 'label', and optional 'hint'
            initial: Initially selected values

        Returns:
            List of selected values or None if cancelled
        """
        initial = initial or []
        print(f"│  {message}")

        for i, choice in enumerate(choices, 1):
            label = choice.get("label", choice.get("value", ""))
            hint = choice.get("hint", "")
            value = choice.get("value", label)
            is_selected = value in initial

            marker = f"{GREEN}✓{RESET}" if is_selected else f"{DIM}○{RESET}"
            hint_str = f" {DIM}({hint}){RESET}" if hint else ""

            print(f"│    {marker} {i}. {label}{hint_str}")

        prompt_str = f"│  Enter numbers separated by comma (e.g., 1,3): "

        try:
            result = input(prompt_str).strip()
            if not result:
                return initial

            selected = []
            for part in result.split(","):
                try:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(choices):
                        value = choices[idx].get("value", choices[idx].get("label"))
                        if value not in selected:
                            selected.append(value)
                except ValueError:
                    pass

            return selected

        except (KeyboardInterrupt, EOFError):
            print()
            return None

    def spinner_message(self, message: str) -> None:
        """
        Display a spinner-style message (simplified, no animation).

        Args:
            message: Message to display
        """
        if self.quiet:
            return
        # Store display width for clearing (not byte length)
        self._last_spinner_width = _display_width(f"│  ◌ {message}...")
        print(f"│  {CYAN}◌{RESET} {message}...", end="", flush=True)

    def spinner_done(self, message: str, success: bool = True) -> None:
        """
        Complete a spinner message.

        Args:
            message: Completion message
            success: Whether the operation succeeded
        """
        if self.quiet:
            return
        symbol = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        # Calculate padding based on display width
        done_width = _display_width(f"│  ✓ {message}")
        clear_width = getattr(self, "_last_spinner_width", 50)
        padding = max(0, clear_width - done_width)
        print(f"\r│  {symbol} {message}" + " " * padding)
