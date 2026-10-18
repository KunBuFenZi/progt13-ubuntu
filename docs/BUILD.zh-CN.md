# 构建指南

## 构建范围

本次发布保存实际工作树的内核修改、最终主线设备树、配置、独立模块源码、运行服务和打包配方。**全新环境中一条命令生成与实机完全一致的可安装系统，尚未验收。** 基础 Image、外置运行模块、Mesa、传感器用户态、libcamera、固件和 Ubuntu 根系统是独立产物，不能只编译 Image 就认为桌面硬件齐全。

历史 `port/build-*`、`prepare-*`、`package-*` 中的数字代表开发阶段，很多脚本读取前一阶段 `out/` 中的摘要、符号或私有归档。保留它们用于追溯修改；新环境优先使用下述入口和源码快照，不依赖本项目作者的构建服务器地址。

## 环境

使用大小写敏感的 Linux 文件系统；不要在 Windows NTFS 内核检出中构建，因为上游有大小写不同的同名文件。实测交叉编译器为 Debian GCC12.2.0。

```sh
sudo apt-get install git build-essential gcc-aarch64-linux-gnu g++-aarch64-linux-gnu \
  bc bison flex libssl-dev libelf-dev device-tree-compiler python3 \
  cpio gzip xz-utils zstd qemu-user-static pkg-config meson ninja-build \
  e2fsprogs gdisk kmod openssl
```

## 内核与设备树

```sh
python3 tools/prepare-kernel.py
JOBS=2 bash tools/build-kernel.sh
```

`kernel/source.json` 固定基线提交；`kernel/patches/0001-tb378fc-platform.patch` 导出构建机实际修改及新增驱动，不是 Windows 大小写冲突产生的差异。`kernel/configs/base.config` 为实机基础内核配置。`kernel/board/sm8750-lenovo-tb378fc-final.dts` 是最终主线DTB反编译后的自包含源码，不含原厂校准。

实机基础内核为 `7.2.0-tb378fc-wifi+`。现有热补丁/独立模块依赖该版本的导出符号和结构布局；换内核后必须重建相应模块，尤其刷新率模块不能直接跨版本使用。

编译后的主线DTB还需按自己的 Lenovo 原厂 base DTB 身份及 dtbo fixups 构造 ABL overlay sink。参考入口为 `third_party/oneplus-integration/tools/build-erhai-abl-symbols.py`，完整参数见其 `--help`。不要使用一加默认的 base index 或其他设备的符号表。实测Lenovo采用本机base11的SM8750P v2身份；该信息不替代对其他固件的读取。

## 外置驱动与用户态

| 部件 | 源码 / 配方 |
|---|---|
| 相机基础模块 | `snapshots/camera74/`：CCI、clocks、GC08A8/OV13B10、V4L2基础 |
| 最终CAMSS | `snapshots/camera-app75/camss/`：替代旧CAMSS，含帧尾/sizeimage对齐修正 |
| DMA heap | `snapshots/camera-app75/heap/` |
| 麦克风IRQ生命周期 | `snapshots/microphone72/codec/`及IRQ补丁 |
| 麦克风原厂ADC映射 | `snapshots/microphone73/codec/`及ADC补丁；SDW使用最终73版，主体codec使用72版 |
| 蓝牙UART | `snapshots/bt-uart-live68b/` |
| PPS诊断 | `snapshots/native-pps71b/`；不负责强制充电电压 |
| 闪光灯 | `snapshots/live-flash70c/`及`port/torch70/` |
| UFS早期overlay | `snapshots/ufs77b-overlay-build/`及`port/build-ufs-write79.py` |
| ext4/JBD2 | `port/build-ext4-78.py`，使用`kernel/configs/ext4.config` |
| 60/120/144Hz | `port/refresh-live76.c`、`refresh-seamless76.h`、`build-refresh-live76.py` |
| 音量方向、电源、触摸OSK | `packaging/device-support/tree/`中最终安装的脚本、systemd和GNOME组件 |
| 音频路由 | `port/Lenovo-TB378FC.m4`及安装树中的ALSA UCM |

模块通过对应SDK的`.config`、`Module.symvers`和依赖模块符号构建，按清单依赖顺序加载。`kernel/configs/`保存本次所用SDK配置；不发布编译二进制或跨版本可直接加载的模块。

libcamera基于0.7.0，应用 `snapshots/patches/libcamera-final.patch`；原始源压缩包由使用者下载。Mesa源及A830v1补丁清单位于 `third_party/oneplus-integration/packaging/mesa/`，OpenGL和Turnip的原始交叉构建配方为`port/build-mesa-cross.py`与`build-vulkan-cross67.py`。传感器用户态的固定来源在`port/sensor-sources.json`。

`packaging/device-support/tree/`是从最终内部安装系统提取的文本文件，优先于早期`port/`副本。它需要已经建好的模块、媒体插件、固件和用户态库；不是可独立安装的软件包。systemd链接另存于`symlinks.json`，Git可执行位按来源保留。

## Ubuntu根系统与初始化

实机使用Ubuntu Desktop26.04 ARM64的`minimal.squashfs`和`minimal.standard.squashfs`下层，ext4中的`upper/`与`work/`提供持久写入。固定ISO及层摘要在`packaging/desktop/source.json`，原始`port/fetch-desktop-base.py`读取它时需复制到本地`inputs/desktop-source.json`。`port/build-persistent-root79.py`记录容器装配方式；它引用的私有settings归档不随仓库提供。应以安装树内容和自行构建的运行依赖创建新的干净upper，而不是复制作者的个人系统。

`initramfs/init`所需输入包括BusyBox静态ARM64、早期ext4/UFS依赖、`/etc/early-modules`、本次根分区UUID、设备固件及`/bin/persistent-shutdown80`。`port/build-initramfs.py`保留已实测的装配器。正式根系统应运行`packaging/setup-owner.sh ACCOUNT`，在本机设置密码、sudo和Snap服务。

## 启动三件套

准备自己的匹配原厂`boot.img`、`init_boot.img`和`vendor_boot.img`放入私有目录，分别用于读取容量和rollback，不会重新读取设备备份。生成私有签名密钥及封装：

```sh
mkdir -p private
openssl genrsa -out private/avb-rsa4096.pem 4096
python3 tools/build-boot-triplet.py \
  --kernel out/kernel-base/arch/arm64/boot/Image \
  --dtb out/abl/erhai-abl.dtb --initramfs out/initramfs/initramfs.cpio.gz \
  --stock private/android --key private/avb-rsa4096.pem \
  --mkbootimg inputs/mkbootimg/mkbootimg.py --avbtool inputs/avb/avbtool.py \
  --output out/gki
```

mkbootimg与avbtool版本见`NOTICE.md`；导出布局与一加`build-mainline-gki.py`、`sign-boot-triplet.py`一致。`out/gki/signed/`是带AVB footer的整分区输出；此命令只生成文件，不连接或刷写设备。公开构建入口的干净重建尚未实机复测，不能把离线自校验当作上机验收。
