# =============================================================================
# TASK RUNNER
# =============================================================================

# Define color codes
BLUE := \033[1;34m
GREEN := \033[1;32m
GH_GREEN := \033[32m
CYAN := \033[1;36m
RED := \033[1;31m
BOLD := \033[1m
GRAY := \033[90m
RESET := \033[0m

# Get remaining arguments after the target
ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# Define a function to execute commands with nice output and handle arguments
# Usage: $(call task,command) - appends ARGS automatically
# Usage: $(call task,command,noargs) - runs command as-is without ARGS
define task
printf "Make => $(BLUE)$(1)$(if $(2),,$(if $(ARGS), $(ARGS)))$(RESET)\n" && \
{ set -a; [ -f .env ] && . .env; set +a; PYTHONPATH=. $(1)$(if $(2),,$(if $(ARGS), $(ARGS))); \
  status=$$?; \
  if [ $$status -eq 130 ]; then \
    printf "\n$(BLUE)Process terminated by user$(RESET)\n"; \
  fi; \
  exit $$status; }
endef

# =============================================================================
# TASKS
# =============================================================================

# Run default demo (instructions)
serve:
	@$(call task,python demo/instructions.py)

# Run function mode demo
serve-function:
	@$(call task,python demo/function.py)

# Run script mode demo
serve-script:
	@$(call task,python demo/script.py)

# Run apps mode demo (FastAPI integration)
serve-apps:
	@$(call task,python demo/apps.py)

# Run container mode demo (Docker)
serve-container:
	@$(call task,python demo/container.py)

# Run all tests
test:
	@$(call task,pytest tests/ -v)

# Release new version
release:
	@$(call task,python utilities/release.py)

list:
	@$(call task,python utilities/issues.py list,noargs)

bug:
	@$(call task,python utilities/issues.py create bug $(ARGS),noargs)

task:
	@$(call task,python utilities/issues.py create task $(ARGS),noargs)

idea:
	@$(call task,python utilities/issues.py create idea $(ARGS),noargs)

resolve:
	@$(call task,python utilities/issues.py resolve $(ARGS),noargs)

delete:
	@$(call task,python utilities/issues.py delete $(ARGS),noargs)

# Prevent Make from treating extra args as targets
%:
	@: