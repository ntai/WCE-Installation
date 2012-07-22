#!/bin/sh

echo "Adding WCE Follow up"
if [ -d /mnt/wce_install_target ] ; then
TARGET=/mnt/wce_install_target
else
TARGET=/mnt/disk2
fi

cd $TARGET
wget -q -O - http://wcesrv/wce-follow-up.tar | tar xf -
disksize_m=$(df -m | grep $TARGET | awk '{print $2}')

# Making sure that the access timestamp and computer-uuid is cleared off
mkdir -p $TARGET/var/lib/world-computer-exchange/
rm -f $TARGET/var/lib/world-computer-exchange/access-timestamp $TARGET/var/lib/world-computer-exchange/computer-uuid

# 
echo -n 'http://wce.footprintllc.com/portals/0/PingBO1.html' > $TARGET/var/lib/world-computer-exchange/access-url

#if [ $disksize_m -ge 34000 ] ; then
#  echo "Adding additional contents"
#  cd $TARGET/usr/local/share/wce/content_archive_v3_Oct_3_11/EN/Program
#  wget --progress=bar -O - http://wcesrv/wce-contents/additional-payload.tar | tar xf -
#fi
sync
echo "Installation complete."
