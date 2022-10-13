git -C /home/prihodpf/repositories/brestprihodpf pull
rsync -av --exclude=".*/" /home/prihodpf/repositories/brestprihodpf/ /home/prihodpf/public_html
chmod 775 /home/prihodpf/public_html
printf "Folder Updated\n"
