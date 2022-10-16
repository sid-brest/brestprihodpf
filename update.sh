git reset --hard
git -C /home/prihodpf/repositories/brestprihodpf pull
rsync -a --exclude=".*/" --exclude='update.sh' --exclude=".git*" /home/prihodpf/repositories/brestprihodpf/ /home/prihodpf/public_html
chmod 775 /home/prihodpf/public_html