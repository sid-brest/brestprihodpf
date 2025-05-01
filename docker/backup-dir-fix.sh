#!/bin/bash
#
# Quick fix script for backup directory permissions
#

echo "Fixing backup directory permissions..."

# Create backup directory if it doesn't exist
sudo mkdir -p /app/backups

# Set liberal permissions to ensure the container can write to it
sudo chmod -R 777 /app/backups

# Try to set ownership to the container user
# First try botuser (the user specified in Dockerfile)
sudo chown -R botuser:botuser /app/backups 2>/dev/null || \
  # If that fails, try UID 1000 which is often the default container user
  sudo chown -R 1000:1000 /app/backups 2>/dev/null || \
  echo "Warning: Could not set ownership, but permissions should work with 777"

# Create a test file to verify permissions
echo "Test file" | sudo tee /app/backups/test_permissions.txt > /dev/null

# Check if the file was created successfully
if [ -f /app/backups/test_permissions.txt ]; then
    echo "✅ Backup directory permissions fixed successfully!"
    # Clean up test file
    sudo rm /app/backups/test_permissions.txt
else
    echo "❌ Could not create test file. Further investigation needed."
fi

# Fix SSH directory as well
echo "Fixing SSH directory permissions..."
sudo mkdir -p /app/ssh
sudo chmod 700 /app/ssh

# Check if SSH key exists
if [ -f /app/ssh/id_rsa ]; then
    sudo chmod 600 /app/ssh/id_rsa
    echo "✅ SSH key permissions fixed!"
else
    echo "⚠️ SSH key not found at /app/ssh/id_rsa"
fi

echo "Done."
