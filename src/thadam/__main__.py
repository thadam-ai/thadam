"""Support python -m thadam using the same entry point as the console script."""

from thadam.cli import main

raise SystemExit(main())
