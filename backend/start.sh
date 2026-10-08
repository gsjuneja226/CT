#!/bin/bash
# CampuShare Backend Startup Script
# ---------------------------------
# This script initializes the database schema and launches the FastAPI server.
set -e

# 1. Initialize Database Schema (Tables and Relationships)
python init.py

# 2. Start the FastAPI server (scheduling handled by background thread)
uvicorn main:app --host 0.0.0.0 --port $PORT
