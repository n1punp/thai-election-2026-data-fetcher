#!/bin/bash
# Thailand Election Data Fetcher

set -e

echo "=== Fetching Election Data ==="
uv run --with httpx python src/fetch_election.py

echo ""
echo "=== Fetching Vote62 Candidate Data ==="
uv run --with httpx python src/fetch_vote62_candidates.py

echo ""
echo "=== Merging Data ==="
uv run python src/merge_election_data.py

echo ""
echo "=== All Done ==="
