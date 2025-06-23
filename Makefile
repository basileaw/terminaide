# Define color codes
BLUE := \033[1;34m
GREEN := \033[1;32m
GH_GREEN := \033[32m
CYAN := \033[1;36m
RED := \033[1;31m
BOLD := \033[1m
GRAY := \033[90m
RESET := \033[0m

# Get remaining arguments after the target for task runner
TASK_ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# Get remaining arguments after the target for issue manager  
ISSUE_ARGS := $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# =============================================================================
# TASK RUNNER
# =============================================================================

# Define a function to execute commands with nice output and handle arguments
# Usage: $(call task,command)
define task
printf "Make => $(BLUE)$(1) $(TASK_ARGS)$(RESET)\n" && \
{ set -a; [ -f .env ] && . .env; set +a; PYTHONPATH=. $(1) $(TASK_ARGS); \
  status=$$?; \
  if [ $$status -eq 130 ]; then \
    printf "\n$(BLUE)Process terminated by user$(RESET)\n"; \
  fi; \
  exit $$status; }
endef

# Run demo server
serve:
	@if [ -z "$(TASK_ARGS)" ]; then \
		$(call task,python demo/instructions.py); \
	elif [ "$(TASK_ARGS)" = "function" ]; then \
		$(call task,python demo/function.py); \
	elif [ "$(TASK_ARGS)" = "script" ]; then \
		$(call task,python demo/script.py); \
	elif [ "$(TASK_ARGS)" = "apps" ]; then \
		$(call task,python demo/apps.py); \
	elif [ "$(TASK_ARGS)" = "container" ]; then \
		$(call task,python demo/container.py); \
	else \
		printf "$(RED)Error:$(RESET) Unknown mode '$(TASK_ARGS)'. Valid modes: function, script, apps, container\n" >&2; \
		exit 1; \
	fi

# Release new version
release:
	@$(call task,python utilities/release.py)

# =============================================================================
# TESTING
# =============================================================================

# Run all tests
test:
	@$(call task,pytest tests/ -v)

# =============================================================================
# ISSUE MANAGER
# =============================================================================

# Create issue: $(call issue_create,Type,label)
define issue_create
@[ -n "$(ISSUE_ARGS)" ] || { printf "$(RED)Error:$(RESET) Please provide a title: make $(MAKECMDGOALS) \"Your issue title\"\n" >&2; exit 1; }; \
set -a; [ -f .env ] && . .env; set +a; \
title="$(ISSUE_ARGS)"; \
repo=$$(git remote get-url origin | sed 's|.*github.com[/:]||; s|\.git$$||'); \
if [ -z "$$GITHUB_TOKEN" ]; then printf "$(RED)Error:$(RESET) GITHUB_TOKEN required for issue creation\n" >&2; exit 1; fi; \
auth_header="Authorization: token $$GITHUB_TOKEN"; \
label_color=$$(curl -s -H "$$auth_header" "https://api.github.com/repos/$$repo/labels" | jq -r '.[] | select(.name=="$(2)") | .color' 2>/dev/null); \
label_escape=$${label_color:+"\033[38;2;$$(printf %d 0x$${label_color:0:2});$$(printf %d 0x$${label_color:2:2});$$(printf %d 0x$${label_color:4:2})m"}; \
label_escape=$${label_escape:-"$(BLUE)"}; \
api_response=$$(curl -s -H "$$auth_header" -H "Content-Type: application/json" -X POST "https://api.github.com/repos/$$repo/issues" -d '{"title":"'"$$title"'","body":"","labels":["$(2)"]}'); \
if echo "$$api_response" | jq -e '.message' >/dev/null 2>&1; then \
	printf "$(RED)Error:$(RESET) %s\n" "$$(echo "$$api_response" | jq -r '.message')"; \
else \
	response=$$(echo "$$api_response" | jq -r '"\(.number) \(.html_url)"'); \
	printf "$(GREEN)✓$(RESET) Created $${label_escape}$(1)$(RESET) $(GH_GREEN)#$${response%% *}$(RESET): $(BOLD)\"$$title\"$(RESET)\n$(GRAY)→ $${response##* }$(RESET)\n"; \
fi
endef

# List issues with dynamic colors: $(call issue_list)
define issue_list
@printf "Make => $(BLUE)Listing GitHub issues$(RESET)\n"; \
set -a; [ -f .env ] && . .env; set +a; \
repo=$$(git remote get-url origin | sed 's|.*github.com[/:]||; s|\.git$$||'); \
auth_header=$${GITHUB_TOKEN:+-H "Authorization: token $$GITHUB_TOKEN"}; \
response=$$(curl -s $$auth_header "https://api.github.com/repos/$$repo/issues?state=open"); \
if echo "$$response" | jq -e '.message' >/dev/null 2>&1; then \
	printf "$(RED)Error:$(RESET) %s\n" "$$(echo "$$response" | jq -r '.message')"; \
elif echo "$$response" | jq -e '. | length' >/dev/null 2>&1 && [ "$$(echo "$$response" | jq '. | length')" = "0" ]; then \
	printf "$(GRAY)No open issues found$(RESET)\n"; \
else \
	labels=$$(curl -s $$auth_header "https://api.github.com/repos/$$repo/labels" | jq -r '.[] | "\(.name):\(.color)"'); \
	printf "$(BOLD)%-6s %-50s %-10s %-12s %s$(RESET)\n" "ID" "TITLE" "LABEL" "AUTHOR" "CREATED"; \
	printf "%-6s %-50s %-10s %-12s %s\n" "------" "--------------------------------------------------" "----------" "------------" "----------"; \
	echo "$$response" | jq -r '.[] | "\(.number)\t\(.title)\t\(.labels[0].name // "")\t\(.user.login)\t\(.created_at)"' | \
	while IFS=$$'\t' read -r num title label user date; do \
		short_date=$$(echo $$date | cut -d'T' -f1); \
		if [ -n "$$label" ]; then \
			label_color=$$(echo "$$labels" | grep "^$$label:" | cut -d: -f2); \
			if [ -n "$$label_color" ]; then \
				r=$$(printf %d 0x$${label_color:0:2}); g=$$(printf %d 0x$${label_color:2:2}); b=$$(printf %d 0x$${label_color:4:2}); \
				label_escape="\033[38;2;$${r};$${g};$${b}m"; \
			else \
				label_escape="$(CYAN)"; \
			fi; \
		else \
			label_escape="$(GRAY)"; \
		fi; \
		printf "$(GH_GREEN)#%-5s$(RESET) %-50.50s $${label_escape}%-10s$(RESET) %-12s %s\n" "$$num" "$$title" "$$label" "$$user" "$$short_date"; \
	done; \
fi
endef

# Process multiple issues: $(call issue_batch,action,command,success_icon,success_msg)
define issue_batch
@printf "Make => $(BLUE)$(4) issues: $(ISSUE_ARGS)$(RESET)\n"; \
set -a; [ -f .env ] && . .env; set +a; \
repo=$$(git remote get-url origin | sed 's|.*github.com[/:]||; s|\.git$$||'); \
auth_header=$${GITHUB_TOKEN:+-H "Authorization: token $$GITHUB_TOKEN"}; \
for issue in $(ISSUE_ARGS); do \
	if response=$$(curl -s $$auth_header "https://api.github.com/repos/$$repo/issues/$$issue" | jq -r '"\(.title) \(.html_url)"' 2>/dev/null) && [ "$$response" != "null null" ]; then \
		title=$$(echo $$response | sed 's/ [^ ]*$$//'); url=$$(echo $$response | awk '{print $$NF}'); \
		if [ "$(1)" = "resolve" ]; then \
			curl -s $$auth_header -X PATCH "https://api.github.com/repos/$$repo/issues/$$issue" -d '{"state":"closed"}' >/dev/null; \
		elif [ "$(1)" = "delete" ]; then \
			curl -s $$auth_header -X DELETE "https://api.github.com/repos/$$repo/issues/$$issue" >/dev/null; \
		fi; \
		printf "$(3)$(RESET) $(4) issue $(GH_GREEN)#$$issue$(RESET): $(BOLD)\"$$title\"$(RESET)$(if $(findstring resolve,$(4)),\n$(GRAY)→ $$url$(RESET))\n"; \
	else \
		printf "$(RED)✗$(RESET) Issue $(GH_GREEN)#$$issue$(RESET) not found\n"; \
	fi; \
done
endef

bug:
	$(call issue_create,Bug,bug)

task:
	$(call issue_create,Task,task)

idea:
	$(call issue_create,Idea,idea)

list:
	$(call issue_list)

resolve:
	$(call issue_batch,resolve,,$(GREEN)✓,Resolved)

delete:
	$(call issue_batch,delete,,$(RED)✔,Deleted)

# Prevent Make from treating extra args as targets
%:
	@: