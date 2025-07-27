# =============================================================================
# TASK RUNNER
# =============================================================================

# Get remaining arguments after the target
ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# Use Python task runner for all tasks
TASK_RUNNER := python -m tools.tasks

# =============================================================================
# ISSUE MANAGEMENT
# =============================================================================

# Include standalone issue management functionality
-include tools/Makefile.issue-manager

# =============================================================================
# PYPI PUBLISHING
# =============================================================================

# Include standalone PyPI publishing functionality
-include tools/Makefile.pypi-publisher

# =============================================================================
# DEMONSTRATIONS
# =============================================================================

# Run function mode demo
serve-function:
	@$(TASK_RUNNER) "python tryit/function.py" $(ARGS)

# Run script mode demo
serve-script:
	@$(TASK_RUNNER) "python tryit/script.py" $(ARGS)

# Run apps mode demo (FastAPI integration)
serve-apps:
	@$(TASK_RUNNER) "python tryit/apps.py" $(ARGS)

# Run container mode demo (Docker)
spin:
	@$(TASK_RUNNER) "docker stop terminaide-container 2>/dev/null || true" $(ARGS)
	@$(TASK_RUNNER) "docker rm terminaide-container 2>/dev/null || true" $(ARGS)
	@$(TASK_RUNNER) "docker build -t terminaide ." $(ARGS)
	@$(TASK_RUNNER) "docker run --name terminaide-container -p 8000:8000 terminaide" $(ARGS)

# =============================================================================
# TESTING
# =============================================================================

# Run all tests
test:
	@$(TASK_RUNNER) "pytest tests/ -v" $(ARGS)

# =============================================================================
# PUBLICATION
# =============================================================================

# Release new version (show usage - use specific targets)
release:
	@echo "Usage: Use specific release targets:"
	@echo "  make release-patch        - Bump patch version and publish (1.0.0 → 1.0.1)"
	@echo "  make release-minor        - Bump minor version and publish (1.0.0 → 1.1.0)"
	@echo "  make release-major        - Bump major version and publish (1.0.0 → 2.0.0)"
	@echo "  make release-dry-run-*    - Simulate any release type"
	@echo "  make release-help         - Show detailed help"

# =============================================================================
# 
# =============================================================================

# Dummy targets to prevent Make errors when passing arguments
%:
	@:
