#!/bin/bash
echo -ne "\033]0;NS Gallery DL Server\007"
./dl.sh -s
read -p "Press any key to continue..."
