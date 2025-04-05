.PHONY: serve release

# Run demo server: make serve function
serve:
	@printf "Make => \033[1;34m"
	-python terminarcade/server.py $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))
	@exit 0

# Release new version: make release patch
release:
	@printf "Make => \033[1;36m"
	python utilities/release.py $(wordlist 2, $(words $(MAKECMDGOALS)), $(MAKECMDGOALS))

# Prevent Make from treating extra args as targets
%:
	@: