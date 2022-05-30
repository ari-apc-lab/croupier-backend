#!/usr/bin/env bash

if [ "$#" -ne 1 ]; then
   echo "usage: setenv.sh <env_file>"
   exit
fi

# Show env vars
grep -v '^#' $1

# Export env vars
export $(grep -v '^#' $1 | xargs)
