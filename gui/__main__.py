"""Allow ``python -m gui``."""

from gui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
