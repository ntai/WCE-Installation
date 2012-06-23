#!/bin/sh

mount --bind /dev/ ./fsimage/dev

cat > ./fsimage/tmp/temp-chores <<EOF
#!/bin/sh
mount -t proc none /proc
mount -t sysfs none /sys
mount -t devpts none /dev/pts
# Things to do
apt-get update
apt-get purge -y --ignore-missing defoma ttf-unifont unifont xfonts-encodings xfonts-unifont x11-common xfonts-utils w3m libxfont1 libfontenc1 libgc1c2
apt-get install -y lm-sensors fancontrol wireless-tools python-dialog xz-utils mg smartmontools wipe pigz lzop kbd
apt-get clean
#
rm -fR /var/cache/apt/* /var/lib/apt/lists/*
dpkg -l > /tmp/dpkg-list
#
umount /proc || umount -lf /proc
umount /sys
umount /dev/pts
EOF

chmod +x ./fsimage/tmp/temp-chores
/usr/sbin/chroot ./fsimage  /bin/sh /tmp/temp-chores
sleep 1
umount ./fsimage/dev
