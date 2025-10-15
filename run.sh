#!/bin/bash
mkdir -p logs
timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
log_file="logs/${timestamp}.log"

poetry run python -m src.main 2>&1 | tee "$log_file"

# chmod +x run.sh
# ./run.sh