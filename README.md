# Ubuntu for Lenovo Xiaoxin Pad Pro GT 13

在联想小新 Pad Pro GT 13（**TB378FC / Snapdragon 8 Elite / SM8750P**）上运行 Ubuntu Desktop 26.04，使用 GNOME 50、Linux 7.2 和 Freedreno / Turnip 图形驱动。

本项目参考并改编 [OnePlus Pad 2 Pro mainline](https://github.com/yzddmr6/onepluspad-2pro-mainline) 的启动封装、设备集成和双系统切换设计。内核以其 [linux-sm8750-erhai](https://github.com/yzddmr6/linux-sm8750-erhai) 为基线，相机还参考了 [Y700 相关内核工作](https://github.com/h0cheung/tb322fc-linux-kernel)。完整来源见 [NOTICE](NOTICE.md)。

## 获取与使用

| 入口 | 内容 |
|---|---|
| [硬件支持](docs/HARDWARE.zh-CN.md) | 已通过真机测试的功能和已知限制 |
| [双系统、安装与恢复](docs/FLASHING.zh-CN.md) | 80GiB Ubuntu 布局、切换方式、恢复步骤 |
| [构建指南](docs/BUILD.zh-CN.md) | 内核补丁、设备树、运行服务和启动镜像 |
| [开发说明](docs/DEVELOPMENT.zh-CN.md) | 目录用途、历史脚本和后续维护 |
| [验证记录](docs/VALIDATION.zh-CN.md) | 实测范围、版本和启动结果 |
| [版本记录](CHANGELOG.md) | 初始源码整理版本 |

**已验证配置**：8GB + 256GB TB378FC，已解锁 Bootloader，Android 16 ColorOS 移植系统。Android 的产品属性会伪装成 OPPO 型号，不能据此判断硬件。其他容量、固件及分区布局未验证。

这是实际设备移植的**源码发布**。当前设备已完成内置安装及 Ubuntu → ColorOS → Ubuntu 往返；仓库不附带个人系统镜像、原厂启动备份、设备校准或签名私钥。完整桌面仍使用独立构建的运行模块，部分开发配方依赖中间产物；尚未提供面向任意设备的一键安装包或从零端到端构建验收。构建与安装文档明确列出这些边界。

## 双系统切换

Ubuntu 使用独立的约 80GiB 分区，Android 数据区约 130GiB。两个系统共用活动 **A 槽**的 `boot`、`init_boot`、`vendor_boot`，切换器将目标三件套整组写入、读回校验，再重启；另一组三件套保存在 Ubuntu 分区。

| 当前系统 | 操作 |
|---|---|
| Ubuntu | 打开应用列表中的“切换到 ColorOS”，输入本机管理员密码。 |
| ColorOS | 在 KernelSU 的 `TB378FC Ubuntu / ColorOS Switch` 模块中点“操作”。 |

切换不重新分区或清空文件。首次划分 Ubuntu 空间会清除 Android 应用和文件，不能直接套用别人的分区表或设备镜像。详见 [安装与恢复](docs/FLASHING.zh-CN.md)。仓库没有通用默认用户密码，管理员账户由设备所有者设置。

## 硬件概况

| 功能 | 当前实测状态 |
|---|---|
| 内屏、背光、触摸 | 3504×2190 整屏；桌面及锁屏触摸正常，60 / 120 / 144Hz 已测。 |
| GPU | Adreno 830v1；GNOME 硬件加速，OpenGL 4.6 / GLES 3.2；Turnip Vulkan 1.4 短测通过。 |
| 无线 | Wi-Fi 7 EHT160 联网；蓝牙扫描、配对及 JBL 蓝牙音箱播放通过。 |
| 音频 | 四路功放播放正常；音量条和音量键可用；第一路麦克风已验证。 |
| 相机 | GC08A8 前摄 / OV13B10 后摄均可出图；分辨率、色彩与对焦仍有局限。 |
| 视频 | Iris H.264 硬编硬解；HEVC 硬编及 HEVC / VP9 / AV1 硬解短测通过。 |
| 旋转 | 四个方向画面及触摸已由用户确认。 |
| USB-C | 外屏 1080p60 扩展桌面、扩展坞 USB 鼠标均已实测。 |
| 充电 | PPS 外部功率计实测约 40～45W。 |
| 电源 | 电源键熄屏与锁屏唤醒已测；长期待机功耗和完整休眠回归未完成。 |

更多限制见[硬件支持表](docs/HARDWARE.zh-CN.md)。光照传感器不在本次适配范围。手写笔、磁吸键盘、DP 音频等未验证项不计为已支持。

## 源码结构

```text
kernel/       固定内核基线、平台补丁、实测配置、最终主线设备树
snapshots/    实际构建的外置模块源码，以及相机/音频修改补丁
initramfs/    内部根分区挂载与关机交接
packaging/    从最终安装系统整理的服务、UCM、桌面组件
switch/       参考一加实现的同槽切换器与 KernelSU 模块模板
tools/        源码准备、启动镜像封装、模块打包、离线验证
port/         原始分阶段构建及调试配方，保留数字版本以便溯源
firmware/     固件清单和自行提取说明，不附带本机私有数据
third_party/  固定版本的参考代码和来源
docs/         构建、安装、支持范围和验证说明
```

## 许可与致谢

设备适配和切换器按 GPL-2.0-only 发布；内核、GNOME、libcamera、Mesa 及其他继承代码保留各自原有许可与作者声明，具体见 [NOTICE](NOTICE.md)。感谢一加项目、Y700 社区和 Linux / Mesa / Ubuntu 上游开发者的工作。
