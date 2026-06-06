# MQTT Discovery 使用指南

## 概述

通过 MQTT Discovery 协议将数据推送到 Home Assistant，实体自动创建，无需手动配置 template。

## MQTT Discovery 优势

- 无需手动配置 template，自动创建实体
- 实体命名与 REST API 方式一致，现有卡片无需修改
- 配置更简单，只需 MQTT Broker 地址和认证信息
- MQTT 协议轻量，retain 消息确保 HA 重启后数据不丢失

## 配置方法

### 1. 确认 Home Assistant MQTT 集成

在 Home Assistant 中启用 MQTT 集成（设置 → 设备与服务 → 添加集成 → MQTT）。

HA 内置的 Mosquitto Broker 插件默认需要认证，账号密码就是你的 HA 登录账号和密码。

### 2. 配置环境变量

编辑 `.env` 文件：

```env
# MQTT Broker 连接（必填）
MQTT_HOST=192.168.1.100        # MQTT Broker 地址（HA 所在主机或 Mosquitto 地址）
MQTT_PORT=1883                 # MQTT 端口（默认 1883）
MQTT_USERNAME=your_ha_username # MQTT 用户名（HA 登录账号，必填）
MQTT_PASSWORD=your_ha_password # MQTT 密码（HA 登录密码，必填）

# 可选配置（通常使用默认值即可）
MQTT_CLIENT_ID=ha_sgcc_electricity
MQTT_TOPIC_PREFIX=homeassistant
MQTT_DEVICE_ID=ha_sgcc_electricity
MQTT_DEVICE_NAME=国家电网电费数据
```

> **重要**：`MQTT_USERNAME` 和 `MQTT_PASSWORD` 是必填项。如果你使用的是 HA 内置的 Mosquitto Broker 插件，这里填写的是 HA 的登录账号和密码（即 MQTT 集成中配置的认证信息）。

### 3. Home Assistant Add-on 配置

在 Add-on 配置中填写：

```yaml
mqtt_host: "192.168.1.100"
mqtt_port: 1883
mqtt_username: "your_ha_username"   # 必填，HA 登录账号
mqtt_password: "your_ha_password"   # 必填，HA 登录密码
mqtt_client_id: "ha_sgcc_electricity"
mqtt_topic_prefix: "homeassistant"
mqtt_device_id: "ha_sgcc_electricity"
mqtt_device_name: "国家电网电费数据"
```

### 4. 推送方式优先级

程序按以下优先级选择推送方式：

1. 如果配置了 `MQTT_HOST`，使用 MQTT Discovery 方式
2. 否则使用 REST API 方式（需要 `HASS_URL` 和 `HASS_TOKEN`）

两种方式不能同时使用。

## 实体命名

MQTT Discovery 版本与 REST API 版本使用相同的实体命名：

| 实体 | 说明 |
|------|------|
| `sensor.electricity_charge_balance_xxxx` | 电费余额（元） |
| `sensor.last_electricity_usage_xxxx` | 最近一天用电量（kWh） |
| `sensor.yearly_electricity_usage_xxxx` | 今年总用电量（kWh） |
| `sensor.yearly_electricity_charge_xxxx` | 今年总电费（元） |
| `sensor.month_electricity_usage_xxxx` | 上月用电量（kWh） |
| `sensor.month_electricity_charge_xxxx` | 上月电费（元） |
| `sensor.month_valley_usage_xxxx` | 当月谷时用电量（kWh） |
| `sensor.month_flat_usage_xxxx` | 当月平时用电量（kWh） |
| `sensor.month_peak_usage_xxxx` | 当月峰时用电量（kWh） |
| `sensor.month_tip_usage_xxxx` | 当月尖时用电量（kWh） |
| `sensor.prepay_balance_xxxx` | 应交金额（元） |
| `sensor.step_used_step1_xxxx` | 阶梯一阶已用电量（kWh，住宅用户） |
| `sensor.step_remain_step1_xxxx` | 阶梯一阶剩余电量（kWh，住宅用户） |
| `sensor.step_used_step2_xxxx` | 阶梯二阶已用电量（kWh，住宅用户） |
| `sensor.step_remain_step2_xxxx` | 阶梯二阶剩余电量（kWh，住宅用户） |
| `sensor.step_used_step3_xxxx` | 阶梯三阶已用电量（kWh，住宅用户） |
| `sensor.step_total_usage_xxxx` | 阶梯累计用电量（kWh，住宅用户） |
| `sensor.step_stage_xxxx` | 阶梯当前阶段（1/2/3，住宅用户） |

> `xxxx` 为户号后四位。

## 设备识别

每个户号会创建一个独立的 HA 设备：

- **设备名称**：`户名（户号后四位）` 或 `国家电网电费-{户号后四位}`
- **制造商**：SGCC
- **型号**：国家电网电费数据获取

## 迁移指南

从 REST API 迁移到 MQTT Discovery：

1. 备份现有 HA 配置
2. 在 `.env` 中添加 `MQTT_HOST`、`MQTT_USERNAME`、`MQTT_PASSWORD`
3. 在 HA 中删除通过 REST API 创建的旧传感器实体
4. 重启 Docker 容器或 Add-on
5. 在 HA 的 设备与服务 → MQTT 中确认新设备和实体已自动创建
6. 实体命名相同，现有卡片无需修改

## 常见问题

### MQTT 连接失败（认证错误）

确认 `MQTT_USERNAME` 和 `MQTT_PASSWORD` 与 HA 中 MQTT 集成配置的认证信息一致。HA 内置 Mosquitto Broker 默认使用 HA 的登录账号密码。

### HA 中看不到 MQTT 实体

1. 确认 HA 中已添加 MQTT 集成（设置 → 设备与服务 → 搜索 MQTT）
2. 检查程序日志中是否显示 "MQTT 连接成功"
3. 使用 MQTT Explorer 等工具确认 `homeassistant/sensor/#` 下有 config 消息
4. 详见 [MQTT 测试指南](MQTT_TEST.md)

### HA 重启后数据会丢失吗？

不会。MQTT 消息设置了 retain 标志，HA 重启后自动恢复最后的传感器状态。

### 能否使用外网 MQTT Broker？

可以，但建议使用内网 Broker 以保证稳定性和安全性。

### MQTT 和 REST API 可以同时使用吗？

不可以。配置了 `MQTT_HOST` 后自动使用 MQTT 方式，否则使用 REST API。
