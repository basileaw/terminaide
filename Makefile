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

# Run default demo (instructions)
serve:
	@$(TASK_RUNNER) "python demo/instructions.py" $(ARGS)

# Run function mode demo
serve-function:
	@$(TASK_RUNNER) "python demo/function.py" $(ARGS)

# Run script mode demo
serve-script:
	@$(TASK_RUNNER) "python demo/script.py" $(ARGS)

# Run apps mode demo (FastAPI integration)
serve-apps:
	@$(TASK_RUNNER) "python demo/apps.py" $(ARGS)

# Run container mode demo (Docker)
serve-container:
	@$(TASK_RUNNER) "python demo/container.py" $(ARGS)

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