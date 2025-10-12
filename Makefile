# =============================================================================
# PORTABLE MAKEFILE INFRASTRUCTURE
# =============================================================================
# This section contains reusable Make utilities that can be copied to any project.
# No project-specific dependencies or assumptions.

# --- Shell Configuration ---
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

# --- Argument Handling ---
# Get remaining arguments after the target
ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# --- ANSI Color Codes ---
GREEN := \\033[32m
BRIGHT_GREEN := \\033[1;32m
RED := \\033[31m
BRIGHT_RED := \\033[1;31m
BLUE := \\033[34m
BRIGHT_BLUE := \\033[1;34m
CYAN := \\033[36m
YELLOW := \\033[33m
BRIGHT_YELLOW := \\033[1;33m
GRAY := \\033[90m
BOLD := \\033[1m
RESET := \\033[0m

# --- Environment Loading ---
# Load environment variables from .env if it exists
ifneq (,$(wildcard .env))
include .env
export
endif

# --- Utility Functions ---
# Execute command with nice output and proper environment setup
define run_command
	@FULL_CMD="$(1)"; \
	if [ -n "$(ARGS)" ]; then \
		FULL_CMD="$(1) $(ARGS)"; \
	fi; \
	echo -e "Make => $(BLUE)$$FULL_CMD$(RESET)"; \
	export PYTHONPATH=.:$$PYTHONPATH; \
	$$FULL_CMD
endef

# --- Dummy Target Handler ---
# Prevent "Nothing to be done" message for arguments
%:
	@:

# =============================================================================
# PROJECT: TERMINAIDE
# =============================================================================
# Everything below this line is specific to the terminaide project

# --- Tool Includes ---
-include tools/Makefile.issue-manager
-include tools/Makefile.pypi-publisher

# --- Demonstrations ---

# Run function mode demo
serve-function:
	$(call run_command,python examples/function.py)

# Run script mode demo
serve-script:
	$(call run_command,python examples/script.py)

# Run apps mode demo (FastAPI integration)
serve-apps:
	$(call run_command,python examples/apps.py)

# --- Docker Operations ---
spin:
	$(call run_command,docker stop terminaide-container 2>/dev/null || true)
	$(call run_command,docker rm terminaide-container 2>/dev/null || true)
	$(call run_command,docker build -t terminaide .)
	$(call run_command,docker run --name terminaide-container -p 8000:8000 terminaide)

# --- Testing ---
test:
	$(call run_command,pytest tests/ -v)

