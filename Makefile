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

# =============================================================================
# TASK RUNNER
# =============================================================================

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

# =============================================================================
# ISSUE MANAGER
# =============================================================================

# Define a function to create GitHub issues with dynamic label colors
# Usage: $(call create_issue,Issue Type,label)
define create_issue
@printf "Make => $(BLUE)Creating $(1)$(RESET)\n" && \
read -p "? Title: " title; \
label_color=$$(gh label list --json name,color | jq -r '.[] | select(.name=="$(2)") | .color' 2>/dev/null); \
if [ -n "$$label_color" ]; then \
	r=$$(printf "%d" 0x$${label_color:0:2}); \
	g=$$(printf "%d" 0x$${label_color:2:2}); \
	b=$$(printf "%d" 0x$${label_color:4:2}); \
	label_escape="\033[38;2;$${r};$${g};$${b}m"; \
else \
	label_escape="$(BLUE)"; \
fi; \
response=$$(echo '{"title":"'$$title'","body":"","labels":["$(2)"]}' | \
gh api repos/:owner/:repo/issues --method POST --input - --template '{{.number}} {{.html_url}}'); \
number=$$(echo $$response | cut -d' ' -f1); \
url=$$(echo $$response | cut -d' ' -f2); \
printf "$(GREEN)✓$(RESET) Created $${label_escape}$(1)$(RESET) $(GH_GREEN)#$$number$(RESET): $(BOLD)\"$$title\"$(RESET)\n$(GRAY)→ $$url$(RESET)\n"
endef

# GitHub issue creation targets
bug:
	$(call create_issue,Bug,bug)

task:
	$(call create_issue,Task,task)

idea:
	$(call create_issue,Idea,idea)

# List GitHub issues
list:
	@printf "Make => $(BLUE)Listing GitHub issues$(RESET)\n" && \
	gh issue list

# Close issues: make close 10 11 12
resolve:
	@printf "Make => $(BLUE)Resolving issues: $(ARGS)$(RESET)\n" && \
	for issue in $(ARGS); do \
		if response=$$(gh issue view $$issue --json title,url --template '{{.title}} {{.url}}' 2>/dev/null); then \
			title=$$(echo $$response | cut -d' ' -f1- | sed 's/ [^ ]*$$//'); \
			url=$$(echo $$response | awk '{print $$NF}'); \
			gh issue close $$issue > /dev/null 2>&1; \
			printf "$(GREEN)✓$(RESET) Resolved issue $(GH_GREEN)#$$issue$(RESET): $(BOLD)\"$$title\"$(RESET)\n$(GRAY)→ $$url$(RESET)\n"; \
		else \
			printf "$(RED)✗$(RESET) Issue $(GH_GREEN)#$$issue$(RESET) not found\n"; \
		fi; \
	done

# Delete issues: make delete 10 11 12  
delete:
	@printf "Make => $(BLUE)Deleting issues: $(ARGS)$(RESET)\n" && \
	for issue in $(ARGS); do \
		title=$$(gh issue view $$issue --json title --template '{{.title}}'); \
		gh issue delete $$issue --yes > /dev/null 2>&1; \
		printf "$(RED)✔$(RESET) Deleted issue $(GH_GREEN)#$$issue$(RESET): $(BOLD)\"$$title\"$(RESET)\n"; \
	done

# Prevent Make from treating extra args as targets
%:
	@: