# Build the image: make build
# Optional: make build IMAGE_NAME=myorg/fractions
IMAGE_NAME ?= fractions

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) .
