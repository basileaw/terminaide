# Define color codes
BLUE := \033[1;34m
RESET := \033[0m

# Get remaining arguments after the target
ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# Define a function to execute commands with nice output and handle arguments
# Usage: $(call task,command)
define task
@printf "Make => $(BLUE)$(1) $(ARGS)$(RESET)\n" && \
{ set -a; [ -f .env ] && . .env; set +a; PYTHONPATH=. $(1) $(ARGS); \
  status=$$?; \
  if [ $$status -eq 130 ]; then \
    printf "\n$(BLUE)Process terminated by user$(RESET)\n"; \
  fi; \
  exit $$status; }
endef

# Define a function to create GitHub issues
# Usage: $(call create_issue,Issue Type,label)
define create_issue
@printf "Make => $(BLUE)Creating $(1) issue$(RESET)\n" && \
read -p "$(1) title: " title; \
gh issue create --label "$(2)" --title "$$title"
endef

# Run demo server
serve:
	$(call task,python demo/server.py)

# Release new version
release:
	$(call task,python utilities/release.py)

# GitHub issue creation targets
bug:
	$(call create_issue,Bug,bug)

task:
	$(call create_issue,Task,task)

idea:
	$(call create_issue,Idea,idea)

issues:
	@printf "Make => $(BLUE)Fetching all issues$(RESET)\n" && \
	gh issue list

# Example of using with a different command
# build:
#	$(call task,npm build)

# Prevent Make from treating extra args as targets
%:
	@:
