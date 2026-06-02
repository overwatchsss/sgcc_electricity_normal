# Release v2.0.0

**发布日期：** 2026-06-02  
**代号：** 多户同步 + 大模型验证码

本版本为 fork 自 [ARC-MX/sgcc_electricity_new](https://github.com/ARC-MX/sgcc_electricity_new) 后的首个 major release，面向 Home Assistant 家庭用户，重点解决**多户号管理、分时电量、企微通知、验证码识别**等痛点。

---

## 亮点

| 能力 | 说明 |
|------|------|
| 企微汇总 | 一次同步推送所有户号余额、用电、当月分时 |
| 当月分时 | 数据库汇总自然月谷/平/峰/尖，写入 HA 传感器 |
| 豆包 LLM | 点选/滑块验证码自动识别，JSON 坐标 + 推理心跳日志 |
| 本地 OCR | 免费本地方案，默认 `CAPTCHA_SOLVER=local` |
| 多户余额 | 修复 Vue 户号切换后余额重复的问题 |
| HA Add-on | 一键安装，支持 SQLite 默认存储 |

---

## 快速开始

### Docker Compose

```bash
docker pull ghcr.io/poiig/ha_sgcc_electricity:v2.0.0
# 或国内加速: ghcr.nju.edu.cn/poiig/ha_sgcc_electricity:v2.0.0
```

配置见 [example.env](../example.env)，完整说明见 [README.md](../README.md)。

### Home Assistant Add-on

仓库地址：`https://github.com/Poiig/ha_sgcc_electricity`  
加载项版本：**2.0.0**

---

## 配置要点

```env
# 验证码（二选一）
CAPTCHA_SOLVER=local          # 默认，免费
# CAPTCHA_SOLVER=llm          # 豆包大模型
# LLM_API_KEY=...
# LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# LLM_MODEL=doubao-seed-2-0-pro-260215

# 数据库（当月分时传感器依赖）
DB_TYPE=sqlite                # 默认

# 企微汇总
PUSH_TYPE=wework
WEWORK_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
WEWORK_PUSH_SUMMARY=true
```

大模型接入详见 **[docs/LLM_CAPTCHA.md](LLM_CAPTCHA.md)**。

---

## 镜像发布

GitHub Release 发布后，请在 Actions 中手动运行 **Build and Push Docker Image**，版本号填 `v2.0.0`，以构建并推送：

- `ghcr.io/poiig/ha_sgcc_electricity:v2.0.0`
- `ghcr.io/poiig/ha_sgcc_electricity:latest`
- Docker Hub（若已配置密钥）：`poiigzhao/ha_sgcc_electricity:v2.0.0`

---

## 完整变更

见项目根目录 [CHANGELOG.md](../CHANGELOG.md)。

---

## 致谢

- [ARC-MX/sgcc_electricity_new](https://github.com/ARC-MX/sgcc_electricity_new)
- [renxiaoyaoo/ha-95598](https://github.com/renxiaoyaoo/ha-95598)
