# 来源与许可

本仓库为 TB378FC 设备适配的集成源码，不将继承代码的作者或许可改为本项目所有。

| 来源 | 固定版本 / 用途 | 许可说明 |
|---|---|---|
| [yzddmr6/onepluspad-2pro-mainline](https://github.com/yzddmr6/onepluspad-2pro-mainline) | `adc57231281ac5bc8eb8ee012ffb04663e9f8226`；GKI 三件套、AVB、ABL overlay sink、切换器、电源与传感器集成参考 | 保留 GPL-2.0-only 文件头；参考代码放在 `third_party/oneplus/`。 |
| [yzddmr6/linux-sm8750-erhai](https://github.com/yzddmr6/linux-sm8750-erhai) | `958a2b4654196bb52dfa0217a0f65ffeaa919f81`；Linux 7.2 SM8750 基线 | Linux 各文件原许可；补丁不取代原许可。 |
| [h0cheung/tb322fc-linux-kernel](https://github.com/h0cheung/tb322fc-linux-kernel) | `bf96c3d4048973298ede78487177c6f1b4f6bc0f`；SM8750 CAMSS、GC08A8 参考 | 保留内核源文件的 SPDX 和作者。来源清单在 `third_party/y700-camera/`。 |
| [GUF296/ubuntu-y700-build-ci](https://github.com/GUF296/ubuntu-y700-build-ci) | 用户指定的 Y700 三代构建/发布方案参考 | 不包含其固件或系统镜像。 |
| libcamera | 0.7.0 / `b7854fd07d42168f099b5ce30d1702e0e0875bf5`；软件 ISP、方向与传感器支持 | 继承文件以 LGPL-2.1-or-later 等原有许可为准；本仓库提供修改补丁。 |
| Mesa | 26.2.3；Freedreno / Turnip，Adreno 830v1 device ID 补丁 | Mesa MIT 等文件级许可；源清单和补丁位于 `third_party/oneplus-integration/packaging/mesa/`。 |
| GNOME Shell | 50；屏幕键盘适配 | `port/gnome/keyboard.js` 及安装树副本继承 GNOME 原有 GPL-2.0-or-later 许可。 |
| AOSP mkbootimg / avbtool | `954bc3ead5e679005fddf3484d247f2557b3c2c9` / `c92ce4cb9a1b6d20a1bc11b7e5864af9f78615bb` | Apache-2.0，工具按固定源码下载，不包含签名私钥。 |

新增设备集成脚本默认 GPL-2.0-only。`LICENSE` 提供 GPL-2.0 许可文本，文件自带的不同许可声明继续适用。

原厂固件、ROM、校准、设备地址、启动镜像备份和用户数据不随仓库分发。`firmware/` 只提供用途、路径与摘要；使用者从自己的设备或合法持有的匹配固件获得输入。
