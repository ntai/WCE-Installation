#!/bin/sh

echo "Adding WCE Follow up"
cd /mnt/disk2
wget -q -O - http://wcesrv/wce-follow-up.tar | tar xf -
disksize_m=$(df -m | grep /mnt/disk2 | awk '{print $2}')

# Making sure that the access timestamp and computer-uuid is cleared off
mkdir -p /mnt/disk2/var/lib/world-computer-exchange/
rm -f /mnt/disk2/var/lib/world-computer-exchange/access-timestamp /mnt/disk2/var/lib/world-computer-exchange/computer-uuid

# 
echo -n 'http://wce.footprintllc.com/portals/0/PingBO1.html' > /mnt/disk2/var/lib/world-computer-exchange/access-url

if [ $disksize_m -ge 34000 ] ; then
  echo "Adding additional contents"
  cd /mnt/disk2/usr/local/share/wce/content_archive_v3_Oct_3_11/EN/Program
  wget --progress=bar -O - http://wcesrv/additional-payload.tar | tar xf -
fi
sleep 3
echo ""
reboot
