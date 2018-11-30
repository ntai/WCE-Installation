#!/usr/bin/python

import subprocess

TARGETS=["live-image/usr/share/locale/calendar",
         "live-image/usr/share/locale/oc",
         "live-image/usr/share/locale/bs",
         "live-image/usr/share/locale/de_CH",
         "live-image/usr/share/locale/ta",
         "live-image/usr/share/locale/nl",
         "live-image/usr/share/locale/es_ES",
         "live-image/usr/share/locale/cy",
         "live-image/usr/share/locale/pt",
         "live-image/usr/share/locale/sq",
         "live-image/usr/share/locale/gu",
         "live-image/usr/share/locale/rw",
         "live-image/usr/share/locale/pt_PT",
         "live-image/usr/share/locale/mk",
         "live-image/usr/share/locale/sv",
         "live-image/usr/share/locale/ne",
         "live-image/usr/share/locale/zh_HK",
         "live-image/usr/share/locale/sk",
         "live-image/usr/share/locale/hu",
         "live-image/usr/share/locale/id",
         "live-image/usr/share/locale/ru",
         "live-image/usr/share/locale/az",
         "live-image/usr/share/locale/mn",
         "live-image/usr/share/locale/wo",
         "live-image/usr/share/locale/gl",
         "live-image/usr/share/locale/nb",
         "live-image/usr/share/locale/it",
         "live-image/usr/share/locale/hu_HU",
         "live-image/usr/share/locale/pa",
         "live-image/usr/share/locale/ms",
         "live-image/usr/share/locale/ast",
         "live-image/usr/share/locale/bg",
         "live-image/usr/share/locale/fr",
         "live-image/usr/share/locale/be@latin",
         "live-image/usr/share/locale/mr",
         "live-image/usr/share/locale/da",
         "live-image/usr/share/locale/eo",
         "live-image/usr/share/locale/hi",
         "live-image/usr/share/locale/ml",
         "live-image/usr/share/locale/nn",
         "live-image/usr/share/locale/de_AT",
         "live-image/usr/share/locale/ko",
         "live-image/usr/share/locale/fr_FR",
         "live-image/usr/share/locale/es",
         "live-image/usr/share/locale/de",
         "live-image/usr/share/locale/mg",
         "live-image/usr/share/locale/hr",
         "live-image/usr/share/locale/ka",
         "live-image/usr/share/locale/ku",
         "live-image/usr/share/locale/vi",
         "live-image/usr/share/locale/th",
         "live-image/usr/share/locale/eu",
         "live-image/usr/share/locale/ca",
         "live-image/usr/share/locale/be-tarask",
         "live-image/usr/share/locale/he",
         "live-image/usr/share/locale/km",
         "live-image/usr/share/locale/wa",
         "live-image/usr/share/locale/ro",
         "live-image/usr/share/locale/fi",
         "live-image/usr/share/locale/be",
         "live-image/usr/share/locale/ja",
         "live-image/usr/share/locale/et",
         "live-image/usr/share/locale/ar",
         "live-image/usr/share/locale/lt",
         "live-image/usr/share/locale/dz",
         "live-image/usr/share/locale/tr",
         "live-image/usr/share/locale/tl",
         "live-image/usr/share/locale/sl",
         "live-image/usr/share/locale/kk",
         "live-image/usr/share/locale/zh_CN",
         "live-image/usr/share/locale/lv",
         "live-image/usr/share/locale/sr",
         "live-image/usr/share/locale/is",
         "live-image/usr/share/locale/ga",
         "live-image/usr/share/locale/pl",
         "live-image/usr/share/locale/zh_TW",
         "live-image/usr/share/locale/cs",
         "live-image/usr/share/locale/pt_BR",
         "live-image/usr/share/locale/uk",
         "live-image/usr/share/locale/de_DE",
         "live-image/usr/share/locale/te",
         "live-image/usr/share/locale/el",
         "live-image/usr/share/locale/sw",
         "live-image/usr/share/locale/bn",
         "live-image/usr/share/locale/rm",
         "live-image/usr/share/locale/nds",
         "live-image/var/apt/*",
         "live-image/var/dpkg/*",
         "live-image/usr/share/drbl/setup/files/SUSE",
         "live-image/usr/share/drbl/setup/files/RH",
         "live-image/usr/share/drbl/setup/files/Ubuntu/12.04",
         "live-image/usr/share/drbl/setup/files/Ubuntu/13.04",
         "live-image/usr/share/drbl/setup/files/Ubuntu/13.10",
         "live-image/usr/share/drbl/setup/files/Ubuntu/12.10",
         "live-image/usr/share/drbl/setup/rpm-md-repos",
         "live-image/usr/share/bug",
         "live-image/usr/share/polkit-1",
         "live-image/usr/share/man",
         "live-image/usr/share/groff",
         "live-image/usr/share/doc",
         "live-image/usr/share/dict",
         "live-image/usr/share/nano",
         "live-image/usr/share/menu",
         "live-image/usr/share/unifont",
         "live-image/usr/share/icons",
         "live-image/usr/share/gnupg",
         "live-image/usr/share/cdrdao",
         "live-image/usr/share/java",
         "live-image/usr/share/vim",
         "live-image/usr/share/applications",
         "live-image/usr/share/images",
         "live-image/usr/local/share/man",
         "live-image/usr/games",
         "live-image/usr/lib/apt",
         "live-image/usr/lib/gnupg",
         "live-image/usr/lib/valgrind",
         "live-image/usr/lib/udisks",
         "live-image/usr/lib/w3m",
         "live-image/usr/lib/refit",
         "live-image/usr/lib/gcc",
         "live-image/usr/lib/pppd",
         "live-image/usr/include/udpcast",
         "live-image/usr/include/btrfs",
         "live-image/var/lib/xfonts",
         "live-image/var/lib/apt",
         "live-image/var/lib/vim",
         "live-image/var/lib/dpkg/parts/*",
         "live-image/var/lib/dpkg/triggers/*",
         "live-image/var/lib/dpkg/updates/*",
         "live-image/var/lib/dpkg/alternatives/*",
         "live-image/var/lib/dpkg/info/*",
         "live-image/var/lib/open-iscsi"]

for target in TARGETS:
    subprocess.call('rm -fR "%s"' % target, shell=True)
    pass
