#!/usr/bin/env python

import os, sys, subprocess, re, string, getpass, time, shutil, uuid, urllib, select

fstab_template = '''# /etc/fstab: static file system information.
#
# Use 'blkid -o value -s UUID' to print the universally unique identifier
# for a device; this may be used with UUID= as a more robust way to name
# devices that works even if disks are added and removed. See fstab(5).
#
# <file system> <mount point>   <type>  <options>       <dump>  <pass>
proc            /proc           proc    nodev,noexec,nosuid 0       0
# / was on /dev/sda1 during installation
UUID=%s /               ext4    errors=remount-ro 0       1
# swap was on /dev/sda5 during installation
UUID=%s none            swap    sw              0       0
'''


nvidia_xorg_conf = '''
Section "ServerLayout"
    Identifier     "Layout0"
    Screen      0  "Screen0" 0 0
    InputDevice    "Keyboard0" "CoreKeyboard"
    InputDevice    "Mouse0" "CorePointer"
EndSection

Section "InputDevice"
    # generated from default
    Identifier     "Mouse0"
    Driver         "mouse"
    Option         "Protocol" "auto"
    Option         "Device" "/dev/psaux"
    Option         "Emulate3Buttons" "no"
    Option         "ZAxisMapping" "4 5"
EndSection

Section "InputDevice"
    # generated from default
    Identifier     "Keyboard0"
    Driver         "kbd"
EndSection

Section "Monitor"
    # HorizSync source: edid, VertRefresh source: edid
    Identifier     "Monitor0"
    Option         "DPMS"
EndSection

Section "Device"
    Identifier     "Device0"
    Driver         "nvidia"
    VendorName     "NVIDIA Corporation"
EndSection

Section "Screen"
    Identifier     "Screen0"
    Device         "Device0"
    Monitor        "Monitor0"
EndSection
'''

pci_re = re.compile(r'\s*[0-9a-f]{2}:[0-9a-f]{2}.[0-9a-f]\s+"([0-9a-f]{4})"\s+"([0-9a-f]{4})"\s+"([0-9a-f]{4})"')

disk_images = []




class mkfs_failed(Exception):
    pass



def detect_video_cards():
    n_nvidia = 0
    n_ati = 0
    n_vga = 0
    lspci = subprocess.Popen("lspci -nm", shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = lspci.communicate()
    for line in out.split('\n'):
        m = pci_re.match(line)
        if m:
            if m.group(1) == '0300':
                vendor_id = m.group(2).lower()
                    # Display controller
                if vendor_id == '10de':
                    # nVidia
                    n_nvidia = n_nvidia + 1
                    pass
                elif vendor_id == '1002':
                    # ATI
                    n_ati = n_ati + 1
                    pass
                else:
                    n_vga = n_vga + 1
                    pass
                pass
            pass
        pass
    return (n_nvidia, n_ati, n_vga)


def uuidgen():
    return str(uuid.uuid1())

def get_filename_stem(p):
    basename = os.path.basename(p)
    while 1:
        ext = ""
        try:
            basename, ext = os.path.splitext(basename)
        except:
            pass
        if ext == "":
            break
        pass
    return basename


def get_router_ip_address():
    netstat = subprocess.Popen("netstat -rn", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (out, err) = netstat.communicate()
    routes_re = re.compile(r'([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+\w+\s+\d+\s+\d+\s+\d+\s+(\w+)')
    for line in out.split('\n'):
        m = routes_re.match(line)
        if m and m.group(1) == '0.0.0.0':
            return m.group(2)
        pass
    return None
            

def is_network_connected():
    connected = False
    try:
        carrier = open("/sys/class/net/eth0/carrier")
        carrier_state = carrier.read()
        carrier.close()
        connected = string.atoi(carrier_state) == 1
    except:
        pass
    return connected
            

class partition:
    def __init__(self):
        self.partition_name = None
        self.partition_type = None
        self.partition_number = None
        pass
    pass


class disk:
    def __init__(self):
        self.device_name = None
        self.partitions = []
        self.disk_type = None
        self.size = None
        self.sectors = None
        self.uuid1 = None
        self.uuid2 = None
        self.mounted = False
        self.partclone_image = "/ubuntu.partclone.gz"
        self.is_disk = None
        self.is_ata_or_scsi = None
        self.is_usb = None
        self.model_name = ""
        self.serial_no = ""
        pass

    def install_ubuntu(self, memsize):
        ask_continue = True
        try:
            self.partition_disk(memsize)
            ask_continue = False
        except mkfs_failed, e:
            pass
        
        if ask_continue:
            yes_no = getpass._raw_input("  mkfs failed continue? ([Y]/n) ")
            if (len(yes_no) > 0) and (yes_no[0].lower() == 'n'):
                sys.exit(0)
                pass
            pass

        # self.restore_disk("/cdrom/ubuntu.dump")

        self.partclone_restore_disk(self.partclone_image)
        self.assign_uuid_to_partitions()
        self.mount_disk()
        self.finalize_disk()
        self.create_wce_tag(self.partclone_image)
        pass


    def partition_disk(self, memsize):
        if not self.sectors:
            parted = subprocess.Popen("parted -s -m %s unit s print" % (self.device_name), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = parted.communicate()
            lines = out.split("\n")
            disk_line = lines[1]
            columns = disk_line.split(":")
            if columns[0] != self.device_name:
                print "parted format changed!? Talk to Tai"
                sys.exit(1)
                pass
            sectors = string.atoi(columns[1][:-1])
            self.sectors = sectors
            pass
        else:
            sectors = self.sectors
            pass
        print "Disk has %d sectors" % sectors

        # Everything is multiple of 8, so that 4k sector problem never happens

        sectors = (sectors / 8) * 8

        # first, memsize and sectors.
        max_swap_sectors = 3 * (((memsize * 1024) / 512) * 1024)
        min_swap_sectors = (((memsize * 1024) / 512) * 1024) / 2
        swap_sectors = sectors / 20
        if swap_sectors > max_swap_sectors:
            swap_sectors = max_swap_sectors
            pass

        if swap_sectors < min_swap_sectors:
            swap_sectors = min_swap_sectors
            pass
        
        part1_start = 2048
        part2_start = ((sectors - part1_start - swap_sectors - 8) / 8) * 8
        part5_start = part2_start + 8
        part1_end = part2_start - 1
        part2_end = sectors - 1 
        part5_end = part2_end

        args = ["parted", "-s", self.device_name, "unit", "s", "mklabel", "msdos", "mkpart", "primary", "ext2", "2048", "%d" % part1_end, "mkpart", "extended", "%d" % part2_start, "%d" % part2_end, "mkpart", "logical", "linux-swap", "%d" % part5_start, "%d" % part5_end, "set", "1", "boot", "on" ]
        print "Executing " + " ".join(args)
        parted = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = parted.communicate()
        pass


    def mkfs_partition_1(self):
        print "mkfs - takes a while, a few minutes"

        mkfs_out = open("/tmp/mkfs.out", "w")
        mkfs_err = open("/tmp/mkfs.err", "w")
        mkfs = subprocess.Popen(["mkfs", "-t", "ext4", "-b", "4096", "%s1" % self.device_name], stdout=mkfs_out, stderr=mkfs_err)
        i = 0
        wheel = "|/-\\"
        while mkfs.returncode is None:
            time.sleep(0.3)
            sys.stdout.write("\r%s" % wheel[ i ])
            sys.stdout.flush()
            i = (i + 1) % len(wheel)
            mkfs.poll()
            pass
        print ""
        print "Done mkfs"
        print ""
        mkfs_out.close()
        mkfs_err.close()
        if mkfs.returncode != 0:
            print "mkfs failed!"
            mkfs_err = open("/tmp/mkfs.err")
            sys.stderr.write(mkfs_err.read())
            mkfs_err.close()
            raise mkfs_failed
        pass


    def assign_uuid_to_partitions(self):
        self.uuid1 = uuidgen()
        self.uuid2 = uuidgen()

        s2 = subprocess.Popen(["tune2fs", "%s1" % self.device_name, "-U", self.uuid1, "-L", "/"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        s2.communicate()
        s3 = subprocess.Popen(["mkswap", "-U", self.uuid2, "%s5" % self.device_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        s3.communicate()
        pass


    def mount_disk(self):
        if self.mounted:
            return

        # Mount it to /mnt/disk2
        if not os.path.exists("/mnt/disk2"):
            os.mkdir("/mnt/disk2")
            pass

        s4 = subprocess.Popen(["mount", "%s1" % self.device_name, "/mnt/disk2"])
        s4.communicate()

        self.mounted = True
        pass


    def restore_disk(self, dump_image_file):
        # Needs to mkfs first for restore
        self.mkfs_partition_1()

        print "restoring disk image"

        self.mount_disk()

        os.chdir("/mnt/disk2")

        # Restore ubuntu 
        print "restore -- this takes about 10-20 minutes"
        restore_out = open("/tmp/restore.out", "w")
        restore_err = open("/tmp/restore.err", "w")
        restore = subprocess.Popen(["restore", "-r", "-f", dump_image_file], stdout=restore_out, stderr=restore_err)
        i = 0
        wheel = "|/-\\"
        while restore.returncode is None:
            time.sleep(0.3)
            restore.poll()
            sys.stdout.write("\r%s" % wheel[ i ])
            sys.stdout.flush()
            i = (i + 1) % len(wheel)
            pass
        pass
        print ""
        print "Done restore"
        print ""
        restore_out.close()
        restore_err.close()
        pass


    def partclone_restore_disk(self, partclone_image_file):
        print "restoring disk image"


        ext = ""
        try:
            ext = os.path.splitext(partclone_image_file)[1]
        except:
            pass
        if ext == ".7z":
            decomp = "7z e -so"
        elif ext == ".gz":
            decomp = "gunzip -c"
        elif ext == ".xz":
            decomp = "unxz -c"
        else:
            decomp = "gunzip -c"
            pass

        if partclone_image_file[0:7] == 'http://':
            retcode = subprocess.call("wget -q -O - '%s' | %s | partclone.ext4 -r -s - -o %s1" % (partclone_image_file, decomp, self.device_name), shell=True)
        else:
            retcode = subprocess.call("%s '%s' | partclone.ext4 -r -s - -o %s1" % (decomp, partclone_image_file, self.device_name), shell=True)
            pass

        if retcode != 0:
            print "\nrestore failed\n"
            sys.exit(1)
            pass

        # Enalrge the ext4 partition. First get partition size
        parted = subprocess.Popen("parted -s -m %s unit s print" % (self.device_name), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = parted.communicate()
        partition_size = None
        for line in out.split('\n'):
            columns = line.split(':')
            if columns[0] == "1":
                partition_size = string.atoi(columns[3][:-1])
                break
            pass

        retcode = subprocess.call("resize2fs -p %s1" % (self.device_name), shell=True)
        pass


    def finalize_disk(self):
        print "Finalizing disk"

        blkid = subprocess.Popen(["blkid"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = blkid.communicate()

        this_disk = re.compile(r'(' + self.device_name + r'\d): ((LABEL=\"[^"]+\") ){0,1}(UUID=\"([0-9a-f-]+)\")\s+TYPE=\"([a-z0-9]+)\"')

        for line in out.split("\n"):
            m = this_disk.match(line)
            if m:
                if m.group(6) == "swap":
                    self.uuid2 = m.group(5)
                elif  m.group(6)[0:3] == "ext":
                    self.uuid1 = m.group(5)
                    pass
                pass
            pass

        print "Primary %s1 - UUID: %s" % (self.device_name, self.uuid1)
        print "Swap    %s5 - UUID: %s" % (self.device_name, self.uuid2)
        
        # patch up the restore
        fstab = open("/mnt/disk2/etc/fstab", "w")
        fstab.write(fstab_template % (self.uuid1, self.uuid2))
        fstab.close()

        newhostname = "wce%s" % self.uuid1[1:8]

        ip = subprocess.Popen(["ip", "addr", "show", "scope", "link"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = ip.communicate()
        mac_addr = ""
        try:
            mac_addr = re.findall("link/ether\s+(..):(..):(..):(..):(..):(..)", out)[0]
            newhostname = "wce%s%s%s" % (mac_addr[3], mac_addr[4], mac_addr[5])
        except:
            pass

        # Set up the /etc/hostname
        hostname_file = open("/mnt/disk2/etc/hostname", "w")
        hostname_file.write("%s\n" % newhostname)
        hostname_file.close()

        # Set up the /etc/hosts file
        hosts = open("/mnt/disk2/etc/hosts", "r")
        lines = hosts.readlines()
        hosts.close()
        hosts = open("/mnt/disk2/etc/hosts", "w")

        this_host = re.compile(r"127\.0\.1\.1\s+[a-z_A-Z0-9]+\n")
        for line in lines:
            m = this_host.match(line)
            if m:
                hosts.write("127.0.1.1\t%s\n" % newhostname)
            else:
                hosts.write(line)
                pass
            pass
        hosts.close()

        #
        # Remove the persistent rules
        # 
        retcode = subprocess.call("rm -f /mnt/disk2/etc/udev/rules.d/70-persistent*", shell=True)

        # It needs to do a few things before chroot
        # Try copy the /etc/resolve.conf
        try:
            shutil.copy2("/etc/resolv.conf", "/mnt/disk2/etc/resolv.conf")
        except:
            # Not a big deal if it does not exist
            pass

        # Now, chroot to the installing disk and do something more

        # Things to do is installing grub
        to_do = "grub-install %s\n" % self.device_name

        # Survey the video card situation
        # Remove the proprietary drivers if not needed.
        # It's particulary important now since Ubuntu developers
        # screwed up the nVidia driver.

        n_nvidia, n_ati, n_vga = detect_video_cards()
        
        if (n_ati > 0) or (n_vga > 0):
            to_do = to_do + "apt-get -q -y --force-yes purge `dpkg --get-selections | cut -f 1 | grep -v xorg | grep nvidia-`\n"
            pass

        chroot_and_exec(to_do)
        pass


    def create_wce_tag(self, image_file_name):
        # Set up the /etc/wce-release file
        release = open("/mnt/disk2/etc/wce-release", "a+")
        print >> release, "wce-contents: %s" % get_filename_stem(image_file_name)
        print >> release, "installation-uuid: %s" % uuidgen()
        pass


    pass


class optical_drive:
    def __init__(self):
        self.device_name = None
        self.features = []
        self.model_name = ""
        self.vendor = ""
        pass

    def get_feature_string(self, sep):
        self.features.sort()
        cd = []
        dvd = []
        rest = []
        for feature in self.features:
            if feature[0:2] == "CD":
                if len(feature[2:]) > 0:
                    cd.append(feature[2:])
                    pass
                else:
                    cd.append("CD")
                    pass
                pass
            elif feature[0:3] == "DVD":
                if len(feature[3:]) > 0:
                    dvd.append(feature[3:])
                    pass
                else:
                    dvd.append("DVD")
                    pass
                pass
            else:
                rest.append(feature)
                pass
            pass
        features = []
        if len(cd) > 0:
            features.append(" ".join(cd))
            pass
        if len(dvd) > 0:
            features.append(" ".join(dvd))
            pass
        return ", ".join(features + rest)

    pass


def chroot_and_exec(things_to_do):
    print "chroot and execute"
    try:
        subprocess.call("mount --bind /dev/ /mnt/disk2/dev", shell=True)
    except:
        pass

    install_script = open("/mnt/disk2/tmp/install-grub", "w")
    install_script.write("""#!/bin/sh
echo "Here we go!"
mount -t proc none /proc
mount -t sysfs none /sys
mount -t devpts none /dev/pts
echo "Here we go!"
#
""")

    install_script.write(things_to_do)

    install_script.write("""#
chmod +rw /boot/grub/grub.cfg
grub-mkconfig -o /boot/grub/grub.cfg
chmod 444 /boot/grub/grub.cfg
umount /proc || umount -lf /proc
umount /sys
umount /dev/pts
""")

    install_script.close()
    
    subprocess.call("chmod +x /mnt/disk2/tmp/install-grub", shell=True)
    chroot = subprocess.Popen(["/usr/sbin/chroot", "/mnt/disk2", "/bin/sh", "/tmp/install-grub"], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = chroot.communicate()
    if chroot.returncode == 0:
        print "grub installation complete."
    else:
        print out
        print err
        pass
    subprocess.call("umount /mnt/disk2/dev", shell=True)
    pass


# disk_re = re.compile(r"([^:]+):([^:]*):([^:]*):([^:]*):([^:]*):([^:]*):([^ ]*) ([^;]*);")
# part_re = re.compile(r"([^:]+):([^:]*):([^:]*):([^:]*):([^:]*):([^:]*):([^;]*);")


disk1_re = re.compile(r"Disk /dev/[^:]+:\s+\d+\.\d*\s+[KMG]B, (\d+) bytes")
disk2_re = re.compile(r"\d+ heads, \d+ sectors/track, \d+ cylinders, total (\d+) sectors")
disk3_re = re.compile(r"Units = sectors of \d+ * \d+ = (\d+) bytes")

part_re = re.compile(r"([^\s]+)\s+\*{0,1}\s+\d+\s+\d+\s+\d+\s+([\dA-Fa-f]+)\s+")


class bad_size(Exception):
    pass


# Memory size in MB
def get_memory_size():
    meminfo = open("/proc/meminfo")
    s = string.atoi(re.findall("MemTotal:\s+ (\d+) kB\n", meminfo.readline())[0]) / 1024
    meminfo.close()
    return s

re_smbios_present = re.compile(r'\s*SMBIOS \d+\.\d+ present.')
re_memory_module_information = re.compile(r'Memory Module Information')
re_socket_designation = re.compile(r'\s*Socket Designation: ([\w\d]+)')
re_enabled_size = re.compile(r'\s*Enabled Size: (\d+) MB')
re_error_status = re.compile(r'\sError Status: (\w+)')

def get_ram_info():
    dmidecode = subprocess.Popen('dmidecode -t 6', shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = dmidecode.communicate()
    # To gurantee the last line flushes out
    out = out + '\n'
    rams = []
    parse_state = 0
    for line in out.split('\n'):
        if parse_state == 0:
            m = re_smbios_present.match(line)
            if m:
                parse_state = 1
                pass
            pass
        elif parse_state == 1:
            m = re_memory_module_information.match(line)
            if m:
                parse_state = 2
                socket_designation = ""
                enabled_size = 0
                memory_status = True
                pass
            pass
        elif parse_state == 2:
            if len(line.strip()) == 0:
                rams.append( (socket_designation, enabled_size, memory_status) )
                parse_state = 1
                continue

            m = re_socket_designation.match(line)
            if m:
                socket_designation = m.group(1)
                pass

            m = re_enabled_size.match(line)
            if m:
                enabled_size = string.atoi(m.group(1))
                pass

            m = re_error_status.match(line)
            if m:
                memory_status = m.group(1).upper() == "OK"
                pass
            pass
        pass
    return rams

# Get ram type
re_memory_type = re.compile(r'\sType: (\w+)')
re_memory_device = re.compile(r'Memory Device')
re_physical_memory = re.compile(r'Physical Memory Array')

def get_ram_type():
    memory_type = None
    dmidecode = subprocess.Popen('dmidecode -t 17', shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = dmidecode.communicate()
    out = out + '\n'
    parse_state = 0
    for line in out.split('\n'):
        if parse_state == 0:
            m = re_smbios_present.match(line)
            if m:
                parse_state = 1
                pass
            pass
        elif parse_state == 1:
            m = re_memory_device.match(line)
            if m:
                parse_state = 2
                pass
            pass
        elif parse_state == 2:
            if len(line.strip()) == 0:
                parse_state = 1
                continue

            m = re_memory_type.match(line)
            if m:
                memory_type = m.group(1)
                pass
            pass
        pass

    if memory_type:
        return memory_type

    dmidecode = subprocess.Popen('dmidecode -t 16', shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = dmidecode.communicate()
    out = out + '\n'
    parse_state = 0
    for line in out.split('\n'):
        if parse_state == 0:
            m = re_smbios_present.match(line)
            if m:
                parse_state = 1
                pass
            pass
        elif parse_state == 1:
            m = re_physical_memory.match(line)
            if m:
                parse_state = 2
                pass
            pass
        elif parse_state == 2:
            if len(line.strip()) == 0:
                parse_state = 1
                continue

            m = re_memory_type.match(line)
            if m:
                memory_type = m.group(1)
                pass
            pass
        pass

    return memory_type


# returns size in MB
def parse_parted_size(size_string):
    if size_string[-1] == "B":
        if size_string[-2] == "M":
            return (int)(string.atof(size_string[:-2]) + 0.5)
        elif size_string[-2] == "G":
            return (int)(string.atof(size_string[:-2]) * 1024 + 0.5)
        else:
            raise bad_size
        pass
    raise bad_size
    pass


#
def find_disk_device_files(devpath):
    result = []
    for letter in "abcdefghijklmnopqrstuvwxyz":
        device_file = devpath + letter
        if os.path.exists(device_file):
            result.append(device_file)
        else:
            break
        pass
    return result


def find_optical_device_files(devpath):
    result = []
    for letter in "0123456789":
        device_file = devpath + letter
        if os.path.exists(device_file):
            result.append(device_file)
        else:
            break
        pass
    return result


def disk_is_a_real_disk(disk_name):
    # I'm going to be optimistic here since the user can pick a disk
    result = True
    try:
        udevadm = subprocess.Popen("udevadm info --query=property --name=%s" % disk_name, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = udevadm.communicate()
        is_ata_or_scsi = False
        is_disk = False
        for line in out.split("\n"):
            if line == "ID_BUS=ata":
                is_ata_or_scsi = True
            elif line == "ID_BUS=scsi":
                is_ata_or_scsi = True
                pass
            elif line == "ID_TYPE=disk":
                is_disk = True
                pass
            if is_ata_or_scsi and is_disk:
                return True
            pass
    except:
        pass
    return result


# This one gets the disks on IDE / SATA only
def get_disks(list_mounted_disks):
    global mounted_devices, mounted_partitions, usb_disks

    disks = []

    # Known mounted disks. 
    # These cannot be the target
    mount = subprocess.Popen(["mount"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (mount_out, muont_err) = mount.communicate()
    mount_re = re.compile(r"(/dev/[a-z]+)([0-9]*) on ([a-z0-9/]+) type ([a-z0-9]+) (.*)")
    mounted_devices = {}
    mounted_partitions = {}
    usb_disks = []
    for line in mount_out.split('\n'):
        m = mount_re.match(line)
        if m:
            device_name = m.group(1)
            if mounted_devices.has_key(device_name):
                mounted_devices[device_name] = mounted_devices[device_name] + ", " + m.group(3)
            else:
                mounted_devices[device_name] = m.group(3)
                pass

            partition_name = m.group(1) + m.group(2)
            mounted_partitions[partition_name] = m.group(3)
            pass
        pass

    # Gather up the possible disks
    possible_disks = find_disk_device_files("/dev/hd") + find_disk_device_files("/dev/sd")
    
    for disk_name in possible_disks:
        # Let's out right skip the mounted disk
        if mounted_devices.has_key(disk_name) and (not list_mounted_disks):
            continue

        # Now, I do double check that this is really a disk
        is_ata_or_scsi = False
        is_disk = False
        is_usb = False
        disk_model = None
        disk_serial = None

        try:
            udevadm = subprocess.Popen("udevadm info --query=property --name=%s" % disk_name, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = udevadm.communicate()
            is_ata_or_scsi = False
            is_disk = False
            for line in out.split("\n"):
                try:
                    elems = line.split('=')
                    tag = string.strip(elems[0])
                    value = string.strip(elems[1])
                    if tag == "ID_BUS":
                        if value.lower() == "ata" or value.lower() == "scsi":
                            is_ata_or_scsi = True
                            pass
                        elif value.lower() == "usb":
                            is_usb = True
                            pass
                        pass
                    elif tag == "ID_TYPE":
                        if value.lower() == "disk":
                            is_disk = True
                            pass
                        pass
                    elif tag == "ID_MODEL":
                        disk_model = value
                        pass
                    elif tag == "ID_SERIAL":
                        disk_serial = value
                        pass
                    pass
                except:
                    pass
                pass
            pass
        except:
            pass

        if not is_disk:
            continue

        # Disk to look at
        current_disk = None
        fdisk = subprocess.Popen(["fdisk", "-l", "-u", disk_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = fdisk.communicate()

        looking_for_partition = False

        for line in out.split("\n"):
            if looking_for_partition and current_disk:
                m = part_re.match(line)
                if m:
                    if current_disk:
                        part = partition()
                        part.partition_name = m.group(1)
                        part.partition_type = m.group(2)
                        current_disk.partitions.append(part)
                        pass
                    pass
                pass
            else:
                if line == "":
                    looking_for_partition = True
                    continue
                m = disk1_re.match(line)
                if m:
                    print "Found a disk"
                    current_disk = disk()
                    current_disk.device_name = disk_name
                    current_disk.mounted = mounted_devices.has_key(current_disk.device_name)
                    current_disk.size = string.atoi(m.group(1)) / 1000000
                    current_disk.sectors = string.atoi(m.group(1)) / 512
                    pass
                pass
            pass

        if current_disk:
            current_disk.is_ata_or_scsi = is_ata_or_scsi
            current_disk.is_usb = is_usb
            current_disk.is_disk = is_disk
            current_disk.model_name = disk_model
            current_disk.serial_no = disk_serial

            if is_ata_or_scsi:
                disks.append(current_disk)
            elif is_usb:
                usb_disks.append(current_disk)
                pass
            pass
        else:
            print "Did not find the disk %s" % disk_name
            pass
        pass

    return disks


def detect_optical_drives():
    opticals = []

    # Gather up the possible devices
    possible_opticals = find_optical_device_files("/dev/sr")
    
    for optical in possible_opticals:
        current_optical = None
        features = []
        is_cd = False
        vendor = ""
        model_name = ""
        try:
            udevadm = subprocess.Popen("udevadm info --query=property --name=%s" % optical, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = udevadm.communicate()
            for line in out.split("\n"):
                elems = line.split('=')
                tag = string.strip(elems[0])
                value = string.strip(elems[1])
                if tag == "ID_TYPE":
                    if value.lower() == "cd":
                        current_optical = optical_drive()
                        pass
                    pass
                elif tag == "ID_CDROM":
                    if value == "1":
                        is_cd = True
                        pass
                    pass
                elif tag[0:9] == "ID_CDROM_":
                    if value == "1":
                        feature = tag[9:].replace('_', '-')
                        if feature == "DVD-PLUS-R":
                            features.append("DVD+R")
                        elif feature == "DVD-PLUS-RW":
                            features.append("DVD+RW")
                        elif feature == "DVD-PLUS-R-DL":
                            features.append("DVD+R(DL)")
                        else:
                            features.append(feature)
                            pass
                        pass
                    pass
                elif tag == "ID_VENDOR":
                    vendor = value
                elif tag == "ID_MODEL":
                    model_name = value
                    pass
                pass
            pass
        except:
            pass

        if is_cd and (current_optical != None):
            current_optical.features = features
            current_optical.vendor = vendor
            current_optical.model_name = model_name
            opticals.append(current_optical)
            pass
        pass
        
    return opticals




def mount_usb_disks():
    global mounted_devices, mounted_partitions, usb_disks, wce_disk_image_path
    index = 1
    for disk in usb_disks:
        for part in disk.partitions:
            mounted = False
            if mounted_partitions.has_key(part.partition_name):
                mounted = True
            else:
                if part.partition_type == '83':
                    mount_point = "/mnt/usb%02d" % index
                    index = index + 1
                    if not os.path.exists(mount_point):
                        retcode = subprocess.call("mkdir %s" % mount_point, shell=True)
                    else:
                        retcode = 0
                        pass
                    if retcode == 0:
                        retcode = subprocess.call("mount %s %s" % (part.partition_name, mount_point), shell=True)
                        pass
                    if retcode == 0:
                        mounted = True
                        mounted_partitions[part.partition_name] = mount_point
                        pass
                    pass
                pass
            if mounted:
                wce_disk_image_path.append(os.path.join(mounted_partitions[part.partition_name], "wce-disk-images"))
                pass
            pass
        pass
    pass


def get_live_disk_images():
    global wce_disk_image_path
    images = []
    for image_path in wce_disk_image_path:
        try:
            for image in os.listdir(image_path):
                path = os.path.join(image_path, image)
                try:
                    if os.path.isfile(path):
                        images.append(path)
                        pass
                    pass
                except:
                    pass
                pass
            pass
        except:
            pass
        pass
    return images


def get_net_disk_images():
    images = []
    urls = []
    urls = urls + ["http://wceinstall/wce-disk-images.txt",
                   "http://wcesrv/wce-disk-images.txt"]

    for url in urls:
        try:
            wget = subprocess.Popen("wget -q -O - -T 3 --dns-timeout=3 %s" % url, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = wget.communicate()
            if wget.returncode == 0:
                for line in out.split('\n'):
                    if (len(line) > 8) and (line[0:7] == 'http://'):
                        images.append(line)
                        pass
                    pass
                pass
            pass
        except Exception, e:
            print url
            print str(e)
            pass
        if len(images) > 0:
            break
        pass
    return images


def choose_disk_image(prompt, images):
    choosing = True

    if len(images) == 1:
        return images[0]

    while choosing:
        print ""
        print prompt
        index = 1
        for image in images:
            if index == 1:
                print "  %2d (default) : %s" % (index, image)
            else:
                print "  %2d           : %s" % (index, image)
                pass
            index = index + 1
            pass
        print "Please choose a disk image file by number (default=1): "
        selection = None
        for t in range(10, 0, -1):
            i, o, e = select.select( [sys.stdin], [], [], 1)
            if i:
                selection = sys.stdin.readline().strip()
                break
            sys.stdout.write("\r %2d " % t)
            sys.stdout.flush()
            pass

        if (selection == None) or len(selection) == 0:
            break

        try:
            return images[string.atoi(selection)-1]
        except Exception, e:
            print e
            choosing = False
            break
        pass
    return images[0]
    pass


def detect_ethernet():
    ethernet_detected = False
    ip = subprocess.Popen(["ip", "addr", "show", "scope", "link"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = ip.communicate()
    try:
        mac_addr = re.findall("link/ether\s+(..):(..):(..):(..):(..):(..)", out)[0]
        if len(mac_addr[3]) > 0:
            ethernet_detected = True
            pass
    except:
        pass
    return ethernet_detected



def detect_sound_device():
    detected = False
    try:
        for snd_dev in os.listdir("/dev/snd"):
            if snd_dev[0:3] == 'pcm':
                detected = True
                break
            pass
        pass
    except:
        pass
    return detected


def try_hook(hook_name):
    urls = []
    router_ip_address = get_router_ip_address()
    if router_ip_address:
        urls.append("http://%s/%s.py" % (router_ip_address, hook_name))
        urls.append("http://%s/%s.sh" % (router_ip_address, hook_name))
        pass

    for url in urls:
        print "Wait..."
        try:
            wget = subprocess.Popen("wget -q -O - -T 2 --dns-timeout=2 %s" % url, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (out, err) = wget.communicate()
            if wget.returncode == 0:
                basename = os.path.basename(url)
                tmpfilepath = "/var/tmp/%s" % basename
                tmpfile = open(tmpfilepath, "w")
                tmpfile.write(out)
                tmpfile.close()
                os.chmod(tmpfilepath, 0755)
                file_ext = os.path.splitext(basename)[1]
                if file_ext == ".py":
                    os.execvp("python", ["python", tmpfilepath])
                elif file_ext == ".sh":
                    os.execvp("sh", ["sh", tmpfilepath])
                    pass
                pass
            pass
        except Exception, e:
            pass
        pass
    return


def main():
    global mounted_devices, disk_images
    if not detect_ethernet():
        print """
************************************************************
*        Ethernet Interface is not detected.               *
*  Before shipping, please make sure to add a network NIC. *
************************************************************
"""
        pass

    print "At any point, if you want to interrupt the installation, hit Control-C"

    disk_images = get_net_disk_images() + get_live_disk_images()
    if len(disk_images) <= 0:
        print "There is no disk image on this media or network."
        pass

    disks = get_disks(False)
    targets = []
    index = 1
    n_free_disk = 0
    first_target = None
    print "Detected disks"
    for d in disks:
        if mounted_devices.has_key(d.device_name):
            print "%3d : %s  - mounted %s" % (index, d.device_name, mounted_devices[d.device_name])
        else:
            print "%3d : %s" % (index, d.device_name)
            n_free_disk = n_free_disk + 1
            if n_free_disk == 1:
                first_target = index - 1
                pass
            pass
        index += 1
        pass

    if n_free_disk > 1:
        print " NOTE: Mounted disks cannot be the installation target."

        selection = getpass._raw_input("  space separated: ")
        for which in selection.split(" "):
            try:
                index = string.atoi(which) - 1
                if not disks[index].mounted:
                    targets.append(disks[index])
                else:
                    print "%s is mounted and cannot be the target." % disks[index].device_name
                    pass
            except Exception, e:
                print "Bad input for picking disk"
                raise e
                pass
            pass
        pass
    else:
        if first_target != None:
            targets.append(disks[first_target])
            pass
        pass

    memsize = get_memory_size()
    if len(targets) > 0:

        for target in targets:
            target.partclone_image = choose_disk_image("Please choose a disk image for %s." % target.device_name, disk_images)
            pass

        if len(targets) == 1:
            print ""
            print "Installing to %s with %s" % (disks[first_target].device_name, disks[first_target].partclone_image)
            print "Hit Control-C to stop the installation"
            count = 3
            while count > 0:
                sys.stdout.write("\r     \r %2d " % count)
                sys.stdout.flush()
                time.sleep(1)
                count = count - 1
                pass
            print ""
            pass

        for target in targets:
            target.install_ubuntu(memsize)
            pass
        pass
    else:
        print "**************************************************"
        print " Please make sure a disk exists, and not mounted."
        print "**************************************************"
        pass
    pass


def parse_cpu_info_tag_value(line):
    try:
        elems = line.split(":")
        return string.strip(elems[0]), string.strip(elems[1])
    except:
        return None, None
    pass


def detect_cpu_type():
    max_processor = 0
    cpu_vendor = "other"
    model_name = ""
    cpu_cores = 1
    cpu_class = 1
    bogomips = 0
    cpu_speed = 0
    cpu_64 = False
    cpu_sse2 = False
    cpu_sse = False
    cpu_3dnow = False
    cpu_mmx = False

    for line in open("/proc/cpuinfo").readlines():
        tag, value = parse_cpu_info_tag_value(line)
        if tag == None:
            continue
        elif tag == "processor":
            processor = string.atoi(value)
            if max_processor < processor:
                max_processor = processor
                pass
            pass
        elif tag == 'vendor_id':
            if value == 'GenuineIntel':
                cpu_vendor = "Intel"
            elif value == 'AuthenticAMD':
                cpu_vendor = "AMD"
                pass
            pass
        elif tag == 'cpu MHz':
            cpu_speed = (int)(string.atof(value)+0.5)
            pass
        elif tag == 'model name':
            model_name = value
            pass
        elif tag == 'cpu cores':
            cpu_cores = string.atoi(value)
            pass
        elif tag == 'flags':
            
            for a_flag in value.split(' '):
                flag = a_flag.lower()
                if flag == "lm" or flag == "lahf_lm":
                    cpu_64 = True
                elif flag == "sse2":
                    cpu_sse2 = True
                elif flag == "sse":
                    cpu_sse = True
                elif flag == "3dnow":
                    cpu_3dnow = True
                elif flag == "mmx":
                    cpu_mmx = True
                    pass
                pass
            pass
        elif tag == 'bogomips':
            bogomips = value
            pass
        pass

    cpu_class = 1
    if cpu_64:
        cpu_class = 5
    elif cpu_sse2 or (cpu_3dnow and cpu_sse):
        cpu_class = 4
    elif cpu_sse or (cpu_3dnow and cpu_mmx):
        cpu_class = 3
    elif cpu_mmx:
        cpu_class = 2
        pass

    # Patch up the CPU speed. cpuinfo seems to show the current CPU speed,
    # not the max speed
    cpuinfo_max_freq = "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
    if os.path.exists(cpuinfo_max_freq):
        f = open(cpuinfo_max_freq)
        speed = f.read()
        f.close()
        cpu_speed = string.atol(speed) / 1000
        pass

    return cpu_class, cpu_cores, max_processor + 1, cpu_vendor, model_name, bogomips, cpu_speed


def triage(output):
    global mounted_devices
    cpu_class, cpu_cores, n_processors, cpu_vendor, model_name, bogomips, cpu_speed = detect_cpu_type()
    # Try getting memory from dmidecode
    ram_type = get_ram_type()
    rams = get_ram_info()
    total_memory = 0
    for ram in rams:
        total_memory = total_memory + ram[1]
        pass
    # backup method
    if total_memory == 0:
        total_memory = get_memory_size()
        pass
    disks = get_disks(True)
    n_nvidia, n_ati, n_vga = detect_video_cards()
    sound_dev = detect_sound_device()
    ethernet_detected = detect_ethernet()
    triage_result = True
    
    subprocess.call("clear", shell=True)
    print >> output, "CPU Level: P%d - %dMhz" % (cpu_class, cpu_speed)
    print >> output, "  %s: Cores: %d cores, Bogomips: %s" % (model_name, cpu_cores, bogomips)

    if ram_type == None:
        ram_type = "Unknown"
        pass

    if total_memory < 200:
        print >> output, "RAM Type: %s  Size: %dMbytes -- INSTALL MORE MEMORY" % (ram_type, total_memory)
        triage_result = False
    else:
        print >> output, "RAM Type: %s  Size: %dMbytes" % (ram_type, total_memory)
        pass

    if len(rams) > 0:
        slots = "    "
        for ram in rams:
            slots = slots + "  %s: %d MB" % (ram[0], ram[1])
            pass
        print >> output, slots
        pass
        
    if len(disks) == 0:
        print >> output, "Hard Drive: NOT DETECTED -- INSTALL A DISK"
        triage_result = False
    else:
        print >> output, "Hard Drive:"
        good_disk = False
        for disk in disks:
            if (disk.size / 1000) >= 20:
                good_disk = True
                pass
            print >> output, "     Device %s: size = %dGbytes  %s" % (disk.device_name, disk.size / 1000, disk.model_name)
            pass
        if not good_disk:
            triage_result = False
            pass
        pass

    optical_drives = detect_optical_drives()
    if len(optical_drives) == 0:
        print >> output, "Optical drive: ***** NO OPTICALS: INSTALL OPTICAL DRIVE *****"
        triage_result = False
    else:
        print >> output, "Optical drive:"
        index = 1
        for optical in optical_drives:
            print >> output, "    %d: %s %s" % (index, optical.vendor, optical.model_name)
            print >> output, "       %s" % (optical.get_feature_string(", "))
            index = index + 1
            pass
        pass

    print >> output, "Video:"
    if n_nvidia > 0:
        print >> output, "     nVidia video card = %d" % n_nvidia
        pass
    if n_ati > 0:
        print >> output, "     ATI video card = %d" % n_ati
        pass
    if n_vga > 0:
        print >> output, "     Some video card = %d" % n_vga
        pass

    if (n_nvidia + n_ati + n_vga) <= 0:
        triage_result = False
        pass

    if ethernet_detected:
        print >> output, "Ethernet card: detected"
    else:
        print >> output, "Ethernet card: NOT DETECTED -- INSTALL ETHERNET CARD"
        triage_result = False
        pass
    if sound_dev:
        print >> output, "Sound card: detected"
    else:
        print >> output, "Sound card: NOT DETECTED -- INSTALL SOUND CARD"
        triage_result = False
        pass
    
    return triage_result


def detect_sensor_modules(modules_path):
    if modules_path:
        modules = open(modules_path)
        lines = modules.readlines()
        modules.close()
        its_there = False
        for line in lines:
            if line == '# LM-SENSORS\n':
                its_there = True
                break
            pass
        if its_there:
            return
        pass

    drivers = []
    sd = subprocess.Popen("cat /dev/null | sensors-detect", shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    (out, err) = sd.communicate()
    look_for_chip_driver = 0
    for line in out.split('\n'):
        if look_for_chip_driver == 0:
            if line == '#----cut here----':
                look_for_chip_driver = 1
                pass
            pass
        elif look_for_chip_driver == 1:
            if line == '# Chip drivers':
                look_for_chip_driver = 2
                pass
            pass
        elif look_for_chip_driver == 2:
            if line == '#----cut here----':
                look_for_chip_driver = 0
            else:
                drivers.append(line)
                pass
            pass
        pass

    if len(drivers) > 0:
        if modules_path:
            modules = open(modules_path, 'a+')
            modules.write("# LM-SENSORS\n%s\n#\n" % "\n".join(drivers))
            modules.close()
            pass

        for module in drivers:
            try:
                retcode = subprocess.call("modprobe %s" % module, shell=True)
            except:
                pass
            pass
        pass
    pass


def set_pwm(speed):
    p = "/sys/devices/platform"
    re_pwm = re.compile(r'^pwm[0-9]$')
    re_pwm_enable = re.compile(r'^pwm[0-9]_enable$')

    for node in os.listdir(p):
        pnode = os.path.join(p, node)
        nodes = []
        try:
            nodes = os.listdir(pnode)
        except:
            nodes = []
            pass
        for pdev in nodes:
            try:
                if re_pwm.match(pdev):
                    ppath = os.path.join(pnode, pdev)
                    pwm = open(ppath, "w")
                    pwm.write("%d" % speed)
                    pwm.close()
                    pass
                pass
            except:
                pass
            try:
                if re_pwm_enable.match(pdev):
                    ppath = os.path.join(pnode, pdev)
                    pwm = open(ppath, "w")
                    pwm.write("1")
                    pwm.close()
                    pass
                pass
            except:
                pass
            pass
        pass
    pass
        

def reboot():
    subprocess.call("reboot", shell=True)
    pass



if __name__ == "__main__":
    global mounted_devices, mounted_partitions, usb_disks, wce_disk_image_path, dlg
    try:
        import dialog
        dlg = dialog.Dialog()
    except:
        dlg = None
        pass
    wce_disk_image_path = ["/live/image/wce-disk-images"]

    # To save my sanity
    detect_sensor_modules(None)
    set_pwm(144)

    # Make sure dialog works
    # This also is a way to wait for the network to come up

    has_network = None
    if is_network_connected():
        if dlg:
            try:
                dlg.gauge_start("Thank you for triaging. Please fill the form.", title="Checking network")
                for i in range(0, 19):
                    dlg.gauge_update(1+i*5, "Thank you for triaging. Please fill the form.", update_text=1)
                    time.sleep(1)
                    has_network = get_router_ip_address() != None
                    if has_network:
                        break
                    pass
                dlg.gauge_update(100, "Thank you for triaging. Please fill the form.", update_text=1)
                time.sleep(1)
                dlg.gauge_stop()
            except:
                dlg = None
                pass
            pass
        if not dlg:
            sys.stdout.write( "\nThank you for triaging. Please fill the form.\nChecking network" )
            sys.stdout.flush()
            for i in range(0, 20):
                sys.stdout.write( "." )
                sys.stdout.flush()
                time.sleep(1)
                has_network = get_router_ip_address() != None
                if has_network:
                    break
                pass
            sys.stdout.write( "\n\n" )
            sys.stdout.flush()
            pass
        pass
            
    triage_result = True

    while True:
        # I do this extra work so that I can have a temp file.
        triage_output = open("/tmp/triage.txt", "w")
        triage_result = triage(triage_output)
        triage_output.close()
        result_displayed = False

        if dlg:
            btitle = "Triage Output"
            if not triage_result:
                btitle = "Triage Output - Failed"
                pass
            try:
                if (not has_network) or (not triage_result):
                    dlg.textbox("/tmp/triage.txt", width=76, height=19, cr_wrap=1, backtitle=btitle)
                    pass
                else:
                    triage_output = open("/tmp/triage.txt")
                    report = triage_output.read()
                    triage_output.close()
                    dlg.infobox(report, width=76, height=19, cr_wrap=1, backtitle=btitle)
                    time.sleep(10)
                    pass
                result_displayed = True
            except Exception, e:
                pass
            pass

        # Backup method to display text
        if not result_displayed:
            triage_output = open("/tmp/triage.txt")
            triage_message = triage_output.read()
            triage_output.close()
            sys.stdout.write(triage_message)
            sys.stdout.flush()
            pass

        # Just in case. One more time would not hurt
        has_network = get_router_ip_address() != None
        # If no network, just wait for the machine to reboot.
        if (not has_network) or (not triage_result):
            print ""
            yes_no = getpass._raw_input("Reboot (i=Install)? ([Y]/n/i) ")
            if ((len(yes_no) == 0) or (yes_no[0].lower() == 'y')):
                reboot()
                sys.exit(0)
                pass
            if (len(yes_no) > 0):
                what = yes_no[0].lower()
                if what == 'i':
                    break
                pass
            pass
        else:
            break
        pass

    mount_usb_disks()
    print ""
    print "HIT RETURN TO HOLD"
    n = 10
    step = 1
    while n > 0:
        sin, sout, sx = select.select([sys.stdin.fileno()], [], [], 1)
        sys.stdout.write("\rProceed installation... %3d   " % n)
        sys.stdout.flush()
        if len(sin) > 0:
            sys.stdout.write("\r****************************")
            sys.stdout.flush()
            sys.stdin.read(1)
            step = (step + 1) % 2
            pass
        n = n - step
        pass

    try_hook("pre-installation")
    try:
        main()
        print ""
        print "**********************"
        print "Installation complete."
        print "**********************"
        print ""
        try_hook("post-installation")
        reboot()
        pass
    except (KeyboardInterrupt, SystemExit), e:
        print "Installation interrupted."
        raise e
        pass
    except Exception, e:
        print "Installation interrupted."
        print str(e)
        raise e
        pass
    print "If you want to restart the installation, type\nsudo python %s" % sys.argv[0]
    pass

