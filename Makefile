.PHONY: serve release

# Define color codes
BLUE := \033[1;34m
RESET := \033[0m

# Get remaining arguments after the target
ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# Define a function to execute commands with nice output and handle arguments
# Usage: $(call task,command)
define task
	@printf "Make => $(BLUE)$(1) $(ARGS)$(RESET)\n"
	@$(1) $(ARGS)
	@exit 0
endef

# Run demo server
serve:
	$(call task,python terminarcade/server.py)

# Release new version
release:
	$(call task,python utilities/release.py)

# Example of using with a different command
# build:
#	$(call task,npm build)

# Prevent Make from treating extra args as targets
%:
	@: