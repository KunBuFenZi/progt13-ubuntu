# 双系统、安装与恢复

## 支持边界

已测硬件：联想小新 Pad Pro GT 13 / TB378FC，8GB + 256GB，SM8750P。已测 Android 为 ColorOS 16 移植版；其产品属性伪装为 OPPO，不能作为硬件选板依据。Bootloader 已解锁，Android 中使用 KernelSU。

本仓库提供实际实现源码及已验证布局说明，**当前没有通用首次安装器或可直接刷入的完整公共镜像**。原始分阶段脚本在 `port/`，依赖本地构建产物和设备输入，不应逐个猜测执行。其他容量与固件不能复用下方边界。

## 实测分区布局

沿用一加项目的独立 Linux 根分区与同槽启动三件套轮换。主 UFS LUN 为 251456913408 字节、4096 字节逻辑扇区。

| 分区 | 实测位置 | 大小 |
|---|---|---|
| userdata | 第18项，LBA 6365608～40419071 | 139482988544字节，约129.90GiB |
| ubuntu | 第19项，LBA 40419072～61390842 | 85900374016字节，约80.00GiB |

首次准备保留 userdata 起点和原身份，缩短其末端，再创建 Linux 分区；**Android 应用、账户和文件会清除**，metadata 同时重新初始化。此操作不是对 Android 加密文件系统的无损缩容。其他17个主LUN分区与其他LUN布局保持原状。

以上数值是本次安装记录，不是任意设备的分区命令。重新准备设备时，应使用 `sgdisk` 根据自己的 GPT、userdata GUID/属性和磁盘尺寸生成方案；不能复制本机 GPT、校准或 Android 启动镜像。

Linux 分区顶层结构：

```text
.tb378fc-root                  内容为 tb378fc-root79
layers/minimal.squashfs
layers/minimal.standard.squashfs
upper/                         系统与用户的可写层
work/                          OverlayFS 工作目录
switch/
  android/                     本机原 Android 三件套与 SHA256SUMS
  ubuntu/                      本机签名 Ubuntu 三件套与 SHA256SUMS
  state.json
```

`initramfs/init` 从 `/etc/root-uuid` 找到 ext4 分区，挂载下层和持久可写层后交给 systemd。普通启动不再通过电脑下载约3.6GB RAM根系统。

## 启动格式

- `boot.img`：Android header v4，仅 Image 和内核参数。
- `init_boot.img`：header v4，空的 gzip newc archive。
- `vendor_boot.img`：header v4，实际 initramfs 和匹配 Lenovo ABL 的 DTB。
- 三个文件均按本机原厂分区大小补齐 AVB footer；rollback index 从自己的原镜像读取。
- 内核版本字段使用 `15.0.0`、补丁日期 `2026-07`，与参考实现一致。遗漏这两个字段的候选在本机被 ABL 标记 unbootable，补齐后正常启动。

已测分区容量为 boot/vendor_boot 各96MiB、init_boot 8MiB。不是将 `fastboot boot` 使用的 header v2 镜像直接刷入 boot。`vbmeta`、ABL、recovery 和 B槽未为双系统切换而修改。

## 已安装系统的日常切换

Ubuntu 打开“切换到 ColorOS”，通过 pkexec 授权。Android 在 KernelSU 模块中点“操作”。它们均调用 `switch/tb378fc-switch`，将目标的三个镜像写入活动 A 槽，完整读回SHA后重启。

切换器命令：

```sh
sudo tb378fc-switch status
sudo tb378fc-switch verify
sudo tb378fc-switch to-android
```

Android 执行的是模块中的同一脚本，经 KernelSU BusyBox 运行。Android 会临时挂载 `ubuntu` 分区，使用完卸载。切换器不自动重新备份启动镜像；使用已有、与当前固件相符的本机备份。OTA/KernelSU 更换启动链后，应先更新本机档案，不能将旧三件套混入新的系统。

公开模板将设备身份放到私有配置文件，不硬编码本次设备标识。打包：

```sh
python3 tools/package-switch.py \
  --serial YOUR_ADB_SERIAL --soc-serial YOUR_NUMERIC_SOC_SERIAL \
  --output out/tb378fc-switch.zip
```

生成的 `.device.conf` 在 Ubuntu 安装到 `/etc/tb378fc-switch.conf`，root:root、0600；ZIP 自带同样配置供 KernelSU 模块使用。不要提交该文件。配置化模板仅完成离线测试；实机往返使用的是相同切换逻辑的私有v81构建。

安装模块后需要再次启动 Android 才会完成激活。本次已确认模块 `enabled=true`、`action=true`、`update=false`，不需要用户重复安装。

## 返回 Android 的电脑恢复入口

若切换中断，使用**自己的原镜像**恢复同一活动槽整组三件套。在 bootloader 中确认当前槽后执行，文件名为本机档案中的 `boot.img`、`init_boot.img`、`vendor_boot.img`：

```sh
fastboot -s YOUR_ADB_SERIAL flash boot_a private/android/boot.img
fastboot -s YOUR_ADB_SERIAL flash init_boot_a private/android/init_boot.img
fastboot -s YOUR_ADB_SERIAL flash vendor_boot_a private/android/vendor_boot.img
fastboot -s YOUR_ADB_SERIAL reboot
```

若 A 槽已经标记不可启动，核对三件套完整性后才重设活动 A。此恢复不删除 Ubuntu 分区，也不等于恢复原厂分区布局。不要为了恢复启动再次格式化 userdata；设备仍含非原厂镜像时不要锁回 Bootloader。
