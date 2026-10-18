# Ubuntu / ColorOS 同槽切换器

由一加项目固定提交`adc57231281ac5bc8eb8ee012ffb04663e9f8226`的`erhai-switch`改编，沿用GPL-2.0-only许可与完整三件套读回校验。

两个系统轮流使用活动A槽，非当前系统的三个启动镜像存于Linux分区`/switch/`。Ubuntu根容器挂载于`/run/tb378fc-root`；Android按分区标签`ubuntu`临时挂载。Linux根标记必须是`tb378fc-root79`。

`to-ubuntu`、`to-android`写入boot/init_boot/vendor_boot；`status`、`verify`不写启动分区。`--no-reboot`保留写入、跳过重启；`--dry-run`也跳过写入。已有Android备份只读复用，`stash-android`被禁用。发生失败时停止，不继续重启；保留中断标记。

公开版本使用`/etc/tb378fc-switch.conf`绑定Linux的SoC身份，KernelSU模块使用本地`device.conf`绑定Android物理序列号。配置只读取固定字段，不作为root shell脚本执行。生成方法见[安装与切换说明](../docs/FLASHING.zh-CN.md)。

这里没有镜像，也不是首次分区工具。只有已经具备匹配根布局和完整两组三件套的设备才能切换。不要把一加、Y700或其他TB378FC的三件套作为自己的Android返回档案。
