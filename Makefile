# Variables
IMAGE_NAME = lfnovo/code-expert-mcp
PLATFORMS = linux/amd64,linux/arm64
BUILDER_NAME = multiplatform-builder

# Default target
.PHONY: help
help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

# Setup buildx builder
.PHONY: setup-builder
setup-builder: ## Setup Docker buildx builder for multi-platform builds
	@if ! docker buildx ls | grep -q $(BUILDER_NAME); then \
		echo "Creating buildx builder: $(BUILDER_NAME)"; \
		docker buildx create --name $(BUILDER_NAME) --platform $(PLATFORMS) --use; \
	else \
		echo "Builder $(BUILDER_NAME) already exists"; \
		docker buildx use $(BUILDER_NAME); \
	fi
	docker buildx inspect --bootstrap

# Build multi-platform image and push
.PHONY: build-push
build-push: setup-builder ## Build multi-platform image and push to registry
	docker buildx build \
		--platform $(PLATFORMS) \
		--tag $(IMAGE_NAME):latest \
		--push \
		.

# Build multi-platform image with custom tag and push
.PHONY: build-push-tag
build-push-tag: setup-builder ## Build and push with custom tag (usage: make build-push-tag TAG=v1.0.0)
	@if [ -z "$(TAG)" ]; then \
		echo "Error: TAG is required. Usage: make build-push-tag TAG=v1.0.0"; \
		exit 1; \
	fi
	docker buildx build \
		--platform $(PLATFORMS) \
		--tag $(IMAGE_NAME):$(TAG) \
		--tag $(IMAGE_NAME):latest \
		--push \
		.

# Build for local testing (single platform)
.PHONY: build-local
build-local: ## Build image for local testing
	docker build -t $(IMAGE_NAME):local .

# Clean up builder
.PHONY: clean-builder
clean-builder: ## Remove the buildx builder
	docker buildx rm $(BUILDER_NAME) || true

# Run locally with docker-compose
.PHONY: run
run: ## Run the service locally with docker-compose
	docker-compose up --build

# Stop and clean up
.PHONY: stop
stop: ## Stop docker-compose services
	docker-compose down

# Build and run locally
.PHONY: dev
dev: build-local run ## Build locally and run with docker-compose

ruff:
	ruff check . --fix

tag:
	@version=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	echo "Creating tag v$$version"; \
	git tag "v$$version"; \
	git push origin "v$$version"

