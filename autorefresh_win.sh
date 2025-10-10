
REPO_PATH='/c/VsCodeProj/utility_hub'
INTERVAL=10

cd $REPO_PATH || { echo "Not found $REPO_PATH"; exit 1; }

echo "Autopull run in: $REPO_PATH"
echo "___________________________"

while true; do
    git pull origin develop

    echo "Waiting for...$INTERVAL seconds"
    echo "___________________________"
    sleep "$INTERVAL"

done
