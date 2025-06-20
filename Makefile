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

# Run demo server
serve:
	$(call task,python demo/server.py)

# Release new version
release:
	$(call task,python utilities/release.py)

# Define a function to create GitHub issues
# Usage: $(call create_issue,Issue Type,label)
define create_issue
@printf "Make => $(BLUE)Creating $(1)$(RESET)\n" && \
read -p "? Title: " title; \
response=$$(echo '{"title":"'$$title'","body":"","labels":["$(2)"]}' | \
gh api repos/:owner/:repo/issues --method POST --input - --template '{{.number}} {{.html_url}}'); \
number=$$(echo $$response | cut -d' ' -f1); \
url=$$(echo $$response | cut -d' ' -f2); \
printf "$(GREEN)✓$(RESET) Created $(1) $(GH_GREEN)#$$number$(RESET): $(BOLD)\"$$title\"$(RESET)\n$(GRAY)→ $$url$(RESET)\n"
endef

# GitHub issue creation targets
bug:
	$(call create_issue,Bug,bug)

task:
	$(call create_issue,Task,task)

idea:
	$(call create_issue,Idea,idea)

# List GitHub issues
issues:
	@printf "Make => $(BLUE)Listing GitHub issues$(RESET)\n" && \
	gh issue list

# Close issues: make close 10 11 12
close:
	@printf "Make => $(GREEN)Closing issues: $(ARGS)$(RESET)\n" && \
	gh issue close $(ARGS)

# Delete issues: make delete 10 11 12  
delete:
	@printf "Make => $(RED)Deleting issues: $(ARGS)$(RESET)\n" && \
	gh issue delete $(ARGS) --yes

# Example of using with a different command
# build:
#	$(call task,npm build)

# Prevent Make from treating extra args as targets
%:
	@: