# =============================================================================
# TASK RUNNER
# =============================================================================

# Get remaining arguments after the target
ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# Use Python task runner for all tasks
TASK_RUNNER := python -m tools.task_runner

# =============================================================================
# TASKS
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

# Run all tests
test:
	@$(TASK_RUNNER) "pytest tests/ -v" $(ARGS)

# Release new version
release:
	@$(TASK_RUNNER) "python tools/publisher.py" $(ARGS)

list:
	@$(TASK_RUNNER) "python tools/issue_manager.py list"

bug:
	@$(TASK_RUNNER) "python tools/issue_manager.py create bug $(ARGS)"

task:
	@$(TASK_RUNNER) "python tools/issue_manager.py create task $(ARGS)"

idea:
	@$(TASK_RUNNER) "python tools/issue_manager.py create idea $(ARGS)"

resolve:
	@$(TASK_RUNNER) "python tools/issue_manager.py resolve $(ARGS)"

delete:
	@$(TASK_RUNNER) "python tools/issue_manager.py delete $(ARGS)"

# Prevent Make from treating extra args as targets
%:
	@: